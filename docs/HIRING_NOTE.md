# Note to send (edit the bracketed parts)

**To:** shreyans at mstack dot ai  **Subject:** Built OpsPilot for the AI Product Engineer role

Hi Shreyans,

Instead of a CV, here is something I built with AI: **OpsPilot**, a prototype assistant for the kind of repetitive work a
specialty-chemicals trader does every day. It reads an RFQ, extracts the fields, searches specs/suppliers/shipping notes,
prices the order with deterministic tools, and hands a quote with sources and warnings to a human for approval. It also checks
COAs against specs and generates export documents that refuse to render when they disagree (e.g. 5000 vs 5200 kg).

The design rule I cared most about: **the model never invents a number.** Prices come only from tested Python tools;
validated inputs are pinned so the model cannot change them; every step is audited in a hash-chained log.

- Live demo: [LIVE_DEMO_URL] (login is one click; submit as analyst, approve as approver)
- Code: [GITHUB_URL] · API docs: [API_DOCS_URL]
- Evals: 30 RFQ / 15 COA / 10 document-set / 30 retrieval cases, run by `python evals/run_all.py`. Numbers are in the README
  together with the caveats (synthetic data, tuned extractor, LLM mode needs your own key to measure).

It is an independent prototype on synthetic data; it uses no Mstack information or systems. I'd enjoy walking you through the
trade-offs, including what I would do differently with real data.

Ayush
[phone / LinkedIn / GitHub]
