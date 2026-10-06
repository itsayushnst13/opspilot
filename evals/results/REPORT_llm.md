# OpsPilot evaluation report

Generated 2026-10-06T18:20:57+00:00 · mode **llm** · model gemini-2.5-flash · embedder `gemini-gemini-embedding-001-768` · reference date 2026-10-01 · run took 142.0 s

Datasets: rfq=30, coa=15, consistency=10, retrieval=30. All data is synthetic.

> Every figure below is computed by `evals/run_all.py` against the real pipeline in this run. See *How to read these numbers* in the README for what they do and do not prove.

### RFQ field extraction

| Metric | Result |
|---|---|
| all_fields_exact | 30/30 (100.0%) |

| Field | Exact match |
|---|---|
| product_code | 30/30 (100.0%) |
| quantity_kg | 30/30 (100.0%) |
| purity_min | 30/30 (100.0%) |
| destination_port | 30/30 (100.0%) |
| required_date | 30/30 (100.0%) |
| incoterm | 30/30 (100.0%) |
| customer_name | 30/30 (100.0%) |
| rfq_date | 30/30 (100.0%) |

### Pricing vs independent reference engine

| Metric | Result |
|---|---|
| status_accuracy | 29/30 (96.7%) |
| price_per_kg_exact | 22/23 (95.7%) |
| total_exact | 22/23 (95.7%) |
| selected_option_match | 22/23 (95.7%) |
| warning_set_exact | 30/30 (100.0%) |
| missing_fields_exact | 30/30 (100.0%) |
| critical_warning_precision | 1.0 |
| critical_warning_recall | 1.0 |

### Tool-call correctness (RFQ runs)

| Metric | Result |
|---|---|
| no_failed_tool_calls | 30/30 (100.0%) |
| calculate_quote_last | 29/30 (96.7%) |
| calc_args_match_validated_fields | 29/30 (96.7%) |
| only_whitelisted_tools | 30/30 (100.0%) |
| required_tools_called | 22/23 (95.7%) |
| citations_present | 22/23 (95.7%) |

### COA checker

| Metric | Result |
|---|---|
| verdict_accuracy | 15/15 (100.0%) |
| product_extraction | 15/15 (100.0%) |
| batch_extraction | 15/15 (100.0%) |
| parameters_extraction_exact | 15/15 (100.0%) |
| parameter_status_accuracy | 63/63 (100.0%) |
| unsafe_passes (non-PASS COA judged PASS) | 0 |
| false_alarms (PASS COA flagged) | 0 |

Confusion (expected → got): PASS: {'PASS': 7}; FAIL: {'FAIL': 5}; REVIEW REQUIRED: {'REVIEW REQUIRED': 3}

### Export-document consistency

| Metric | Result |
|---|---|
| clean_sets | 3 |
| inconsistent_sets | 7 |
| exact_finding_set_match | 10/10 (100.0%) |
| detection_rate (inconsistent sets flagged) | 7/7 (100.0%) |
| false_positive_rate (clean sets flagged) | 0/3 (0.0%) |
| finding_precision | 1.0 |
| finding_recall | 1.0 |
| gate_blocks_rendering_after_inconsistent_edit | 4/4 (100.0%) |

### Retrieval (RAG)

| Metric | Result |
|---|---|
| queries | 30 |
| embedder | gemini-gemini-embedding-001-768 |
| hit@1 | 29/30 (96.7%) |
| hit@3 | 29/30 (96.7%) |
| hit@5 | 29/30 (96.7%) |
| mrr | 0.9667 |

| Query kind | hit@3 |
|---|---|
| spec_sheet | 14/14 (100.0%) |
| supplier | 8/8 (100.0%) |
| regulatory | 5/5 (100.0%) |
| shipping | 2/3 (66.7%) |

### Grounding / hallucination

| Metric | Result |
|---|---|
| quote_total_equals_deterministic_tool_result | 22/22 (100.0%) |
| breakdown_arithmetic_reproducible | 22/22 (100.0%) |
| kb_citations_point_to_ingested_documents | 88/88 (100.0%) |
| data_source_refs_resolve_to_files | 86/86 (100.0%) |
| no_price_invented_for_incomplete_rfqs | 7/7 (100.0%) |
| prompt_injection_flagged_and_price_unaffected | 1/1 (100.0%) |

### Latency

| Measure | p50 | p95 | max |
|---|---|---|---|
| RFQ end-to-end (30 runs) ms | 2139 | 4966 | 5227 |
| COA end-to-end (15 runs) ms | 805 | 942 | 1028 |

Tool time p50 1021.1 ms · LLM time p50 0.0 ms · tokens 0. SQLite on a shared sandbox CPU; indicative only. In rules mode there are no model calls, so no LLM time or tokens.

### Known failures (not hidden)

- **pricing**: `{'id': 'RFQ-013', 'status_ok': False, 'warnings_got': [], 'warnings_expected': [], 'price': None, 'price_expected': '5.0228', 'total': None, 'total_expected': '15068.25', 'option': None, 'option_expected': 'MF:23'}`
- **grounding**: `{'id': 'RFQ-013', 'problem': 'no quote'}`
- **retrieval** RET-028: rank None for “How is the hazmat surcharge calculated and what is the minimum freight charge?” (top-3: shipping/shipping_rates.csv, shipping/shipping_rates.csv, shipping/shipping_rates.csv)
