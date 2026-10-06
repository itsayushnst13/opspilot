"""Retrieval evals over the knowledge base: hit@k and MRR against labelled queries."""
from __future__ import annotations

from evals.harness import load, rate


def evaluate() -> dict:
    from app.core.db import SessionLocal
    from app.rag.embed import get_embedder
    from app.rag.retrieve import retrieve

    cases = load("retrieval_cases")
    h1 = h3 = h5 = 0
    rr = 0.0
    by_kind: dict[str, list[int]] = {}
    fails = []
    with SessionLocal() as db:
        emb = get_embedder()
        for c in cases:
            hits = retrieve(db, c["query"], emb, k=5)
            paths = [h.path for h in hits]
            rank = next((i + 1 for i, p in enumerate(paths) if p in c["expected_paths"]), None)
            h1 += rank == 1
            h3 += bool(rank and rank <= 3)
            h5 += bool(rank and rank <= 5)
            rr += 1 / rank if rank else 0
            k = by_kind.setdefault(c["kind"], [0, 0])
            k[0] += bool(rank and rank <= 3)
            k[1] += 1
            if rank != 1:
                fails.append({"id": c["id"], "query": c["query"], "expected": c["expected_paths"], "rank": rank, "top3": paths[:3]})
    n = len(cases)
    return {"queries": n, "embedder": emb.name, "hit@1": rate(h1, n), "hit@3": rate(h3, n), "hit@5": rate(h5, n),
            "mrr": round(rr / n, 4), "hit@3_by_kind": {k: rate(*v) for k, v in by_kind.items()}, "not_top1": fails}
