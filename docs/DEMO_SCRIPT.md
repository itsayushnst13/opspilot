# 2-minute demo script

Setup: open the live URL once beforehand (free hosting sleeps). Have two browser profiles, or just use the one-click role
switch on the login page (Sign out -> pick the other demo user).

| Time | Do | Say |
|---|---|---|
| 0:00 | Login screen, click **Asha Analyst** | "Two roles because high-impact actions need a second person: analyst submits, approver decides." |
| 0:10 | RFQ -> Load demo RFQ -> Process | "5 MT of CHEM-X01, 99% purity, Houston. Synthetic data. This runs the real pipeline." |
| 0:20 | Quote page appears (<1 s) | "Fields extracted, units converted in code: 5 MT = 5,000 kg. The model never does arithmetic." |
| 0:35 | Point at **Sources compared** | "8 feasible sources; it picked the cheapest one that still meets the delivery date. That rule is deterministic." |
| 0:50 | Cost table, then **Warnings** and **Sources & citations** | "Every line is reproducible. INCOTERM_ASSUMED is flagged because the customer didn't say CIF/FOB. Citations point to the spec sheet and pricing rows." |
| 1:05 | Open **Tool calls**, expand `calculate_quote` | "Every tool call, argument and result is recorded: this is the observability and the audit." |
| 1:15 | Sign out -> **Arjun Approver** -> same RFQ -> **Approve** | "Human approval. Critical warnings would force a written reason. Sending to the customer is simulated." |
| 1:30 | **Generate export documents** -> edit packing list net quantity to 5200 | "Four documents from one order. A 5000 vs 5200 mismatch blocks the PDFs instead of silently shipping inconsistent paperwork." |
| 1:50 | Audit trail -> **Verify hash chain** | "Append-only, hash-chained. Edit a row in the database and verification fails." |
| 2:00 | Evaluations page | "Measured numbers, and the caveat banner: synthetic data, tuned extractor, LLM mode not measured here." |

Optional 30 s add-ons: upload `data/coas/COA-008.pdf` (FAIL with explanation); ask the knowledge base "storage conditions for CHEM-X01".

Likely questions and honest answers are in the README "Limitations" section.
