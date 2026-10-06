"""Embedding backends.

* HashingEmbedder - deterministic, offline, dependency-free (feature hashing of unigrams + bigrams).
  Used in tests/CI and when no API key is configured.
* GeminiEmbedder  - Google Gemini embedding API over REST (used when GEMINI_API_KEY is set).
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Protocol

import httpx
import numpy as np

from ..core.config import Settings, get_settings

STOPWORDS = frozenset("""a an and are as at be by for from has have how in is it its of on or that the this to was
what when where which who why will with we our do does can i you your their they them than then there these those
if into not no but also such any all per via""".split())
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for t in TOKEN_RE.findall(text.lower()):
        if t in STOPWORDS:
            continue
        toks.append(t)
        if "-" in t:  # chem-x01 -> chem, x01 as well
            toks.extend(p for p in t.split("-") if p and p not in STOPWORDS)
    return toks


class HashingEmbedder:
    def __init__(self, dim: int = 768):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _vec(self, text: str) -> list[float]:
        toks = tokenize(text)
        feats: dict[str, int] = {}
        for t in toks:
            feats[t] = feats.get(t, 0) + 1
        for a, b in zip(toks, toks[1:]):
            key = f"{a}_{b}"
            feats[key] = feats.get(key, 0) + 1
        v = np.zeros(self.dim, dtype=np.float64)
        for f, tf in feats.items():
            h = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:6], "big") % self.dim
            sign = 1.0 if h[6] & 1 else -1.0
            v[idx] += sign * (1.0 + math.log(tf))
        n = np.linalg.norm(v)
        return (v / n).tolist() if n > 0 else v.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class EmbeddingError(RuntimeError):
    pass


class GeminiEmbedder:
    """Gemini embeddings over REST. NOTE: request/response shapes are covered by mock-transport tests;
    they have not been exercised against the live API in the build environment."""

    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str, dim: int = 768, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        self.api_key, self.model, self.dim = api_key, model, dim
        self.name = f"gemini-{model}-{dim}"
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _post(self, path: str, body: dict) -> dict:
        last: Exception | None = None
        for attempt in range(3):
            try:
                r = self._client.post(f"{self.BASE}/{path}", json=body,
                                      headers={"x-goog-api-key": self.api_key})
                if r.status_code in (429, 500, 502, 503, 504):
                    last = EmbeddingError(f"Gemini returned {r.status_code}")
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                if r.status_code >= 400:
                    raise EmbeddingError(f"Gemini embedding error {r.status_code}")
                return r.json()
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(0.5 * (2 ** attempt))
        raise EmbeddingError(f"Gemini embedding request failed: {last}")

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 50):
            batch = texts[i:i + 50]
            body = {"requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": t}]},
                                  "taskType": task, "outputDimensionality": self.dim} for t in batch]}
            data = self._post(f"models/{self.model}:batchEmbedContents", body)
            embs = data.get("embeddings", [])
            if len(embs) != len(batch):
                raise EmbeddingError("Gemini returned an unexpected number of embeddings")
            for e in embs:
                v = np.asarray(e["values"], dtype=np.float64)
                n = np.linalg.norm(v)
                out.append((v / n if n > 0 else v).tolist())
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


_cached: dict[str, Embedder] = {}


def get_embedder(settings: Settings | None = None) -> Embedder:
    s = settings or get_settings()
    key = f"{s.gemini_api_key is not None}-{s.gemini_embed_model}-{s.embed_dim}-{s.llm_mode}"
    if key not in _cached:
        if s.gemini_api_key and s.llm_mode != "rules":
            _cached[key] = GeminiEmbedder(s.gemini_api_key, s.gemini_embed_model, s.embed_dim, s.llm_timeout_s)
        else:
            _cached[key] = HashingEmbedder(s.embed_dim)
    return _cached[key]
