# OpsPilot: AI-assisted chemical operations assistant

> **This is an independent prototype built using synthetic data and does not use Mstack's proprietary information or systems.**

OpsPilot takes a customer RFQ (request for quotation) and turns it into a **suggested quote with sources, warnings and a full
audit trail, waiting for human approval**. It also checks certificates of analysis (COA) against specifications and generates
export documents that refuse to render when they contradict each other.

| | |
|---|---|
| Live demo | https://opspilot-69g5.onrender.com/ (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)) |
| API docs | https://opspilot-69g5.onrender.com/docs |
| Code | https://github.com/itsayushnst13/opspilot |
| Demo script | [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) (2 minutes) |

> **Status, honestly.** Built and tested locally (backend tests on SQLite and PostgreSQL 16, real-browser run of the whole UI) and
> deployed on Render. The Docker image could not be built in the build environment; the production layout was simulated and the
> Render deploy runs the same app. LLM (Gemini) mode is implemented and tested against a mock transport and a scripted fake model only;
> **it has not been run successfully against the live Gemini API**. A first live attempt (October 2026) failed and the app fell back to
> rules mode as designed. All reported metrics are for the deterministic "rules" mode.

---

## 1. Problem
A specialty-chemicals trader answers the same kinds of requests all day: "quote 5 MT of product X at 99% purity delivered to
Houston", "is this batch's certificate within spec?", "prepare the shipping paperwork". Each answer needs data from a dozen places
(supplier price lists, manufacturing costs, freight tables, spec sheets, regulatory notes, past quotes), and each mistake
(wrong unit, expired price, mismatched quantity between invoice and packing list) is expensive.

## 2. Why this matters
These workflows are repetitive, rule-heavy and document-heavy, which is exactly where AI helps, **and** where an AI that "sounds
right" but invents a price or silently changes a quantity is dangerous. The interesting engineering problem is not calling an LLM;
it is deciding what the model is allowed to do and proving it stays inside those lines.

## 3. Solution
* The **language model reads and routes**; **deterministic code decides and calculates**.
* Every price, margin, freight and tolerance is computed by tested Python tools from reference data. The model cannot produce a price.
* Validated inputs are pinned, outputs are checked for grounding, failures are visible, and a person approves anything high-impact.

## 4. Architecture diagram
Full diagram and request flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
User -> React dashboard -> FastAPI (auth, validation)
     -> Workflow layer: parse > extract > normalize (code) > agent
          |- RAG (chunk/embed/search, citations)      -> kb tables
          |- Tool registry (pricing, shipping, quality, doc checks) -> reference data
          '- Documents (PDF generation, consistency gate)
     -> Guardrails (pinned args, grounded summary, injection flag, forced steps)
     -> Human approval (roles, four-eyes, reasons) -> Final action (quote PDF; sending simulated)
     -> Audit log (SHA-256 hash chain)            [PostgreSQL / SQLite]
```

## 5. Main workflows
1. **RFQ -> quote (P0).** Upload PDF/TXT or paste text -> extract fields -> retrieve product knowledge -> compare feasible
   suppliers and the in-house plant including shipping and deadline -> cost build-up and margin -> quote with warnings, citations and
   a summary -> approver decides -> quote PDF -> audit. Missing information produces `needs_info` and **no price**.
2. **COA checker (P1).** Extract product, batch and measured parameters; compare with the specification using exact arithmetic;
   verdict **PASS / FAIL / REVIEW REQUIRED** with a per-parameter explanation.
3. **Export documents (P2).** Commercial invoice, packing list, certificate of origin and shipping instruction from one
   structured order; a cross-document checker blocks PDFs when fields disagree (e.g. 5000 vs 5200 kg).
4. **Knowledge base.** Ask questions over specs, suppliers, pricing, shipping and regulatory notes; answers cite their passages.
5. **Audit + observability + evals.** Hash-chained audit UI, per-run latency/tool/LLM/token metrics, and an evaluation page.

Pages: `/dashboard`, `/rfq`, `/quality`, `/documents`, `/knowledge-base`, `/audit`, `/evaluations`.

## 6. Tech stack
Python 3.13, FastAPI, SQLAlchemy 2, Pydantic v2, PostgreSQL 16 (SQLite for tests/local), pypdf, openpyxl, reportlab, NumPy,
PyJWT, httpx · React 19, TypeScript, Vite, Tailwind CSS 4 · Gemini REST API (optional) · Docker, Render, Neon (config provided).
About 4,300 lines of backend, 1,100 of frontend, 600 of tests, 1,900 of evals and data generation.

## 7. Agent architecture
`RFQOrchestrator` has two modes behind the same whitelisted tool registry (`search_product`, `get_product_spec`,
`search_knowledge_base`, `get_supplier_price`, `get_manufacturing_cost`, `recommend_source`, `get_shipping_cost`, `calculate_quote`):

* **rules mode** (default, no API key): regex extractor + fixed tool plan. Deterministic and what the metrics measure.
* **llm mode** (Gemini key set): the model extracts literal fields (JSON schema) and drives a function-calling loop.

Model names get retired, so the client takes a primary model (`GEMINI_MODEL`) and an ordered fallback list
(`GEMINI_FALLBACK_MODELS`), remembers the one that answered, and forgets it again once it stops working.
`python scripts/check_gemini.py` lists the models the account can actually call and makes one real
generation request; it reads the key from `.env` and never prints it.

Every failure is classified so a rules fallback is never mistaken for a successful model run:

| Category | What happens |
|---|---|
| `auth` (401/403) | Stops immediately - another model cannot fix a rejected key |
| `model_missing` (404, or a 400 naming the model) | Tries the next configured model, and forgets a cached one |
| `rate_limit` (429), `outage` (5xx), `timeout`, `network` | Up to 3 attempts with backoff, then the next model |
| `invalid_request` (other 4xx) | Stops immediately; an optional `thinkingLevel` is dropped and retried once |
| `blocked` | Stops immediately (a safety block is not a transport problem) |

A whole call is bounded by `LLM_TOTAL_BUDGET_S` (default 90 s) so an outage cannot multiply into minutes of
retries. `/api/health` and `/api/dashboard` report `llm.configured` and `llm.verified` separately, with the
last error category, so "a key is set" is never shown as "the model works".

**Live measurements** (one real call each, personal free-tier key, 11 October 2026, `--compare`). Thinking
tokens dominate the latency of a trivial call, and the default model matters more than anything else:

| Model | `GEMINI_THINKING_LEVEL` | Latency | Thinking tokens | Total tokens |
|---|---|---|---|---|
| `gemini-3.6-flash` | `minimal` | **1,420 ms** | 0 | 9 |
| `gemini-3.6-flash` | `low` | 1,421 ms | 66 | 75 |
| `gemini-3.6-flash` | default | 1,829 ms | 90 | 99 |
| `gemini-3.8-flash` | default | 6,320 ms | 92 | 101 |
| `gemini-3.8-flash` | default (first call of a session) | 49,875 - 76,136 ms | 85 - 95 | 94 - 104 |

So the defaults are `GEMINI_MODEL=gemini-3.6-flash` with `gemini-3.8-flash` and `gemini-2.5-flash` behind it.
`thinkingLevel` has to be nested under `generationConfig.thinkingConfig`; sent flat the API rejects it, which
the client detects, drops and retries once, and `check_gemini.py` prints when that happens.

Both go through the same safety rails:

| Rail | What it does |
|---|---|
| Literal extraction + code normalizer | The model returns strings as written ("5 MT"); unit conversion, dates and port resolution are code |
| Pinned arguments | product, quantity, purity, incoterm, port and dates are overwritten with the validated values if the model changes them; each override is logged |
| Single price source | Only `calculate_quote` returns a price, and its `option_id` is re-validated for feasibility |
| Forced steps | If the model never calls `calculate_quote`, the workflow runs the rules plan and adds `AGENT_STEP_FORCED` |
| Grounded summary | Any number in the model's summary that is not in a tool result causes the summary to be replaced by a template (`SUMMARY_REJECTED`) |
| Fallbacks | LLM outage or invalid JSON -> rules mode, flagged (`LLM_UNAVAILABLE`) |
| Whitelist + schema validation | Unknown tools and invalid arguments are rejected and recorded |

## 8. RAG architecture
Parse (PDF/TXT/CSV/XLSX) -> chunk (~900 chars, line-based with one-line overlap; table rows rendered as `column: value; ...`)
-> embed -> store in `kb_chunks` -> exact cosine search with a product-code boost -> passages with citations like
`specifications/CHEM-X01_spec_sheet.pdf (page 1)`. The seeded corpus is 54 documents / 235 chunks (ingests in ~0.2 s).
* **Embedder:** a deterministic hashing embedder (signed feature hashing of unigrams and bigrams, 768 dims) by default; a Gemini embedder is available (mock-tested only).
  The hashing embedder is **lexical, not semantic**: it works on this corpus because queries share vocabulary with documents.
* **No pgvector** (not available where this was built, unnecessary at this size): exact search in NumPy behind one function, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
* Users can upload documents into the knowledge base; they are treated as untrusted text.

## 9. Human-in-the-loop design
Roles `analyst`, `approver`, `admin`. The creator of a quote cannot approve it (four-eyes, configurable). A quote with critical
warnings can only be approved with a written reason. Rejection needs a reason. Approval only makes the PDF downloadable;
**sending to the customer is simulated.** Decisions are audited with the approver, reason and acknowledged warnings.

## 10. Guardrails
Agent rails above, plus: upload allow-list, magic-byte checks, 5 MB limit, XLSX zip-bomb guard, safe filenames, stored under the
run id; JWT auth with role checks; login and submission rate limits (in-memory, single process); prompt-injection detection
(`PROMPT_INJECTION_SUSPECTED`, critical); no stack traces to clients; secrets only from environment variables
(`.env.example` provided, `.env` ignored); production refuses to start with the default JWT secret.
Business rules: [docs/BUSINESS_RULES.md](docs/BUSINESS_RULES.md).

## 11. Evaluation methodology
`python evals/run_all.py` runs the real pipeline (upload -> background job -> tools -> database) in an isolated database and
computes every metric; nothing is hard-coded. Datasets live in `evals/datasets/`, generated with the data (`seed 42`):

* **30 RFQs** (PDFs; clean, hazmat, FOB, tiered volume, lbs, "5 MT", dates without year, missing quantity/destination, unknown product,
  unavailable purity, below MOQ, expired prices, infeasible/tight deadline, history deviation, one prompt injection).
* **15 COAs** (7 pass, 5 fail, 3 review) in different layouts · **10 document sets** (3 clean, 7 with injected inconsistencies) · **30 retrieval queries**.
* **Pricing ground truth** comes from an *independent reference implementation* (`scripts/datagen/reference.py`) that does not share
  code with the production engine.
* **Agent guardrail scenarios** use a scripted fake model that tries to tamper with arguments, skip tools, invent a price, call a forbidden tool, etc.
* `pytest` (73 tests) covers API flows, roles, upload security, Gemini request/response handling on a mock transport, audit tamper detection and
  concurrent writers. They pass on SQLite and on PostgreSQL 16. Sanity-checked by deliberately breaking the pinning logic and the audit lock: the relevant tests fail.

## 12. Real evaluation results
<!-- RESULTS:START -->
Mode: **rules**, generated 2026-10-11T17:44:03+00:00, embedder `hashing-768`. Full report: [`evals/results/REPORT.md`](evals/results/REPORT.md).

| Check | Cases | Result | Caveat |
|---|---|---|---|
| RFQ field extraction (all 8 fields exact) | 30 RFQ PDFs | 30/30 (100.0%) | Rules extractor was tuned on this set: optimistic |
| Pricing: price/kg exact vs reference engine | 23 priceable RFQs | 23/23 (100.0%) | Reference engine written for this project |
| Pricing: selected source matches | 23 | 23/23 (100.0%) |  |
| Warning set exact / critical precision & recall | 30 | 30/30 (100.0%) / 1.0 & 1.0 |  |
| Tool calls: calculate_quote last, args match validated fields | 30 | 30/30 (100.0%); 30/30 (100.0%) | Rules-mode fixed plan |
| Agent guardrails vs a scripted misbehaving model | 7 scenarios | 7/7 (100.0%) | Fake LLM, not Gemini |
| COA verdict accuracy | 15 COA PDFs | 15/15 (100.0%) | Unsafe passes: 0; false alarms: 0 |
| COA parameters extracted exactly | 15 | 15/15 (100.0%) | Template-generated PDFs |
| Document-set consistency: exact finding match | 10 sets | 10/10 (100.0%) | 7 inconsistent, 3 clean |
| Blocked-render gate after a bad edit | 4 | 4/4 (100.0%) |  |
| Retrieval hit@1 / hit@3 / MRR | 30 queries | 28/30 (93.3%) / 29/30 (96.7%) / 0.95 | Embedder: hashing-768 (lexical hashing). Misses listed in the report |
| Quote total equals deterministic tool result | 23 | 23/23 (100.0%) |  |
| KB citations point to indexed documents | 94 citations | 94/94 (100.0%) | Checks the document exists, not that it supports the claim |
| No price produced for incomplete RFQs | 7 | 7/7 (100.0%) |  |
| Prompt-injection RFQ flagged, price unaffected | 1 | 1/1 (100.0%) | One case |
| RFQ end-to-end latency p50 / p95 (ms) | 30 runs | 27 / 42 | Rules mode, SQLite, sandbox CPU. No LLM latency measured |
<!-- RESULTS:END -->

**How to read these numbers.** They show the pipeline does what it was designed to do on data it was designed around. They do **not** show
real-world accuracy:
* All data is synthetic and template-generated, so the format variety is far narrower than real RFQs and COAs.
* The rules extractor was developed while looking at the 30 RFQs (one failing field, `customer_name`, was fixed after seeing the failures), so extraction is an optimistic, tuned number.
  A later manual try of a free-text RFQ (`Customer: X`) exposed a case the eval set did not cover, and was fixed afterwards: the set is evidently not exhaustive.
* One consistency case was adjusted so that its expected findings are physically coherent (a packing-list quantity change must also change gross weight).
* The pricing "reference" was written by the same author, so shared misunderstandings of the business rules would not be caught.
* **LLM-mode accuracy, latency and token cost are not measured.** Run `GEMINI_API_KEY=... python evals/run_all.py --llm` to produce them.
* Latency numbers are from rules mode on a shared sandbox CPU and SQLite.

## 13. Screenshots
| | |
|---|---|
| ![Quote](docs/screenshots/04-rfq-approval.png) **Suggested quote, sources compared, warnings, approval panel** | ![Docs blocked](docs/screenshots/07-documents-blocked.png) **5000 vs 5200 kg blocks the document set** |
| ![COA](docs/screenshots/08-coa-fail.png) **COA FAIL with explanation** | ![Evals](docs/screenshots/11-evaluations.png) **Evaluations page with caveats** |
| ![Dashboard](docs/screenshots/02-dashboard.png) **Dashboard** | ![Audit](docs/screenshots/10-audit.png) **Hash-chained audit trail** |

More in [`docs/screenshots/`](docs/screenshots/) (login, KB, mobile).

## 14. Demo
Script: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). The reference scenario: **5 MT CHEM-X01, 99% purity, Houston** -> 5,000 kg, 8 feasible sources compared, the
cheapest one that meets the delivery date selected, price/kg and total with a reproducible breakdown, `INCOTERM_ASSUMED` flagged, citations to the spec sheet and
pricing rows, approve as a second user, then generate the export documents. Demo logins are one click on the login page.

## 15. Local setup
```bash
# 1. data (already in the repo; this regenerates it with identical content)
python scripts/generate_data.py

# 2. backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env          # defaults run in rules mode on SQLite
uvicorn app.main:app --reload    # http://localhost:8000/docs

# 3. frontend (new terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api)

# 4. tests and evals
cd backend && pytest                                  # TEST_DATABASE_URL=postgresql://... to run on Postgres
python evals/run_all.py                               # from the repo root
python scripts/render_readme_results.py               # refresh the results table above
```
Or `docker compose up --build` for Postgres + the app on http://localhost:8000.
Demo logins: `analyst@opspilot.demo`, `approver@opspilot.demo`, `admin@opspilot.demo` (password from `DEMO_PASSWORD`, default `opspilot-demo`).
Add `GEMINI_API_KEY` to `.env` to enable LLM mode, then `python scripts/check_gemini.py` to confirm the key,
the available models and one real generation call before trusting it.

## 16. Deployment
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): one Render web service (Dockerfile serves UI + API) with a free Neon/Supabase Postgres, or UI on Vercel + API on Render.
`render.yaml`, `Dockerfile`, `docker-compose.yml` and `frontend/vercel.json` are included. Free tiers sleep, so open the URL before a demo.
Pin `REFERENCE_DATE` for a long-lived demo: the synthetic price lists expire on 2027-03-31 and the sample RFQs are dated October 2026.

## 17. Limitations
* **A fallback can look like a successful LLM run, so the report now says which path ran.** The first `--llm`
  eval returned 100% everywhere with `mode: llm` in its header - and 0 tokens and 0 ms of model time against a
  14 s median run, which is the signature of every call failing and falling back to rules. `LLM_UNAVAILABLE` is
  not one of the codes the pricing eval compares, so the fallback did not show up in any score. The report now
  counts `runs_that_used_the_model` and refuses to present a fallback as an LLM result.
* **Gemini mode generates, but its accuracy is still unmeasured.** `scripts/check_gemini.py` now passes against
  the live API, so the transport, model selection and fallback paths are real rather than mock-only. What is
  *not* measured is extraction and tool-calling quality in LLM mode: every accuracy figure in this README is
  from rules mode. `evals/results/REPORT_llm.md` is from an earlier run whose generation calls were all failing
  (0 generation tokens), so it reflects only the Gemini embedder; see the note at its top. Run
  `python evals/run_all.py --llm` to replace it.
* **Free-tier rate limits.** Comparison calls and the first `--llm` eval both came back 429. Generation degrades
  to rules mode with `LLM_UNAVAILABLE`; a rate-limited *embedding* used to abort the whole run, which is fixed -
  the knowledge-base tool now records a failed call and the quote continues without those passages. Embeddings
  have their own quota, so `EMBEDDER=hashing` (the default for `python evals/run_all.py --llm`, override with
  `--gemini-embeddings`) keeps retrieval identical between the two modes and off that quota.
* **Synthetic everything.** Prices, specs, suppliers, margins and rules are invented. Real data would need real ingestion, validation, and domain review of the rules.
* **Extraction is brittle outside the tested formats** in rules mode (regex). LLM mode should generalise better but is unmeasured. Scanned PDFs (no text layer) are not supported; there is no OCR.
* **Retrieval is lexical** (hashing embedder), so paraphrased questions can miss. Two of 30 eval queries do not rank first, and RET-029 is not retrieved at all.
* **Citations prove a document was retrieved, not that it supports a claim**; in rules mode the knowledge base returns passages rather than a generated answer.
* **Audit tamper-evidence, not tamper-proofing:** the hash chain detects edits; it does not stop a DB admin rewriting the whole chain. The ORM blocks updates/deletes but there is no Postgres trigger or external anchoring.
* Rate limiting is in-memory (single process). Auth is demo-grade (shared demo password, 8-hour tokens, no refresh/rotation, no SSO).
* Quote "sending" is simulated; there is no email, ERP or CRM integration. Quotes are single-currency (USD), single customer tier (`standard`).
* Background jobs run in-process (FastAPI background tasks): fine for a demo, not for a durable queue.
* The process-wide embedding index is cached in memory per process; multiple workers would each build their own.
* No load testing; no accessibility audit.

## 18. Future improvements
Live Gemini evaluation and a model comparison; a real embedding model plus pgvector (or hybrid BM25 + vectors) and a reranker; OCR for scanned COAs;
a durable job queue; Postgres trigger or external anchoring for the audit log; SSO and per-customer margin tiers; ERP/email integration
behind the approval step; a labelled set of real (anonymised) RFQs to replace the synthetic one; regression evals in CI.

---
Layout: `backend/` (FastAPI app + tests) · `frontend/` (React UI) · `data/` (synthetic reference data and documents) · `evals/` (datasets, runner, results) ·
`scripts/` (data generator) · `docs/` (architecture, rules, deployment, demo, screenshots).
