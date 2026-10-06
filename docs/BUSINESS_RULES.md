# Business rules (synthetic, documented so they can be audited)

All rules live in deterministic Python (`backend/app/tools/pricing_engine.py`, `quality.py`, `doc_validation.py`). They are
invented for this prototype; they are **not** any real company's pricing policy. The language model never computes a price.

## Sourcing options for an RFQ
An option is either a **supplier price row** or an **in-house plant** option.

| Rule | Detail |
|---|---|
| Purity | Option grade must be >= the requested minimum purity (spec minimum if none requested; `PURITY_ASSUMED`). |
| Price validity | Supplier price rows must be valid on the RFQ date (`valid_until >= rfq_date`). Expired rows are excluded and counted. |
| Volume tier | The highest supplier price tier with `tier_min_kg <= quantity` applies. Supplier MOQ must be <= quantity. |
| Plant | Quantity must be between the plant's minimum batch and capacity. |
| No source | If nothing qualifies: `NO_FEASIBLE_SOURCE` (critical), no price. |

## Choosing the option
1. Add shipping (origin country -> destination port) to every option: transit days, freight rate.
2. Keep options whose `lead_time + transit_days <= days available` (RFQ date to required date).
3. Pick the **cheapest** of those. Tie-break: price, then lead time, then option id.
4. If none meets the deadline, pick the cheapest overall and raise `DEADLINE_INFEASIBLE` (critical).

## Cost build-up
| Line | Formula |
|---|---|
| Material | `quantity_kg x price_per_kg`, rounded to cents (ROUND_HALF_UP) |
| Ocean freight (CIF only) | `max(rate_per_kg x qty, min_charge)` |
| Hazmat surcharge (CIF, hazardous products) | `freight x surcharge_pct` |
| Insurance (CIF only) | `0.5% x material cost` |
| Handling | `0.04 USD/kg x qty` |
| **Landed cost** | sum of the lines |
| Margin | from the margin table by product category x quantity tier x customer tier |
| **Selling price** | `landed / (1 - margin)`, cents; price per kg to 4 decimals |

* **Incoterms:** FOB excludes freight, surcharge and insurance. CIF is the default, and is also assumed for unsupported
  terms (DAP, DDP, EXW ...), with `INCOTERM_ASSUMED`.
* **Quote validity:** 14 days from the RFQ date.
* **History check:** if >= 2 historical quotes exist for the product and the new price per kg differs from their median by
  more than 15 %, `DEVIATION_FROM_HISTORY`.

## Warning catalogue
| Severity | Codes |
|---|---|
| critical (approver must write a reason to approve) | MISSING_FIELD, UNKNOWN_PRODUCT, PURITY_UNAVAILABLE, NO_FEASIBLE_SOURCE, NO_SHIPPING_RATE, DEADLINE_INFEASIBLE, PROMPT_INJECTION_SUSPECTED |
| warning | DEADLINE_TIGHT (< 7 days slack), PRICE_VALIDITY_SHORT (price expires inside the 14-day quote validity), INCOTERM_ASSUMED, DEVIATION_FROM_HISTORY, OPTION_NOT_CHEAPEST, PURITY_ASSUMED, UNIT_ASSUMED, DATE_AMBIGUOUS, AGENT_STEP_FORCED |
| info | HAZMAT, DELIVERY_DATE_MISSING, UNIT_CONVERTED, LLM_UNAVAILABLE, SUMMARY_REJECTED |

With missing required fields (product, quantity, or destination for CIF) the system returns `needs_info` and **no price**.

## Approval
* Roles: `analyst` (submits), `approver` (decides), `admin` (both).
* Four-eyes: the creator of a quote cannot decide on it unless `ALLOW_SELF_APPROVAL=true`.
* A quote with any critical warning can only be approved with a written reason (>= 10 characters); rejections need a reason (>= 5).
* Approval makes the quote PDF downloadable. Sending to the customer is **simulated**.

## COA verdicts (`check_quality`)
Each specified parameter has a limit, a `review_margin` and a `critical` flag. Exact `Decimal` arithmetic.

| Situation | Result |
|---|---|
| Within limits | PASS |
| Misses a limit by <= review margin | REVIEW REQUIRED |
| Misses by more than the margin, **critical** parameter | FAIL |
| Misses by more than the margin, non-critical | REVIEW REQUIRED |
| Required parameter not reported, or batch number missing | REVIEW REQUIRED |
| Product cannot be identified | REVIEW REQUIRED |

The overall verdict is the worst parameter result. It is decision support: a person confirms.

## Export documents
One structured order produces the commercial invoice, packing list, certificate of origin and shipping instruction.
`check_documents` compares: product code, HS code, net quantity, consignee, origin, destination port, gross weight,
package count (all critical) and incoterm (warning), plus arithmetic: invoice total = qty x unit price (tolerance
`max(0.01, qty x 0.00005 + 0.005)` because the unit price is shown to 4 decimals), packages x unit weight = net, gross >= net.
If any finding exists the run is **blocked**: no PDF can be downloaded until an edit makes the set consistent again.
