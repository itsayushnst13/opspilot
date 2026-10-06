"""Destination port resolution."""
from __future__ import annotations

import difflib
import re

PORT_ALIASES = {
    "Houston": ["houston", "port of houston", "houston tx", "houston texas", "houston usa", "houston us", "ushou"],
    "Los Angeles": ["los angeles", "port of los angeles", "los angeles ca", "los angeles usa", "uslax", "la port"],
    "Savannah": ["savannah", "port of savannah", "savannah ga", "savannah usa", "ussav"],
    "Rotterdam": ["rotterdam", "port of rotterdam", "rotterdam netherlands", "rotterdam nl", "nlrtm"],
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def resolve_port(raw: str | None, known_ports: list[str]) -> tuple[str | None, bool]:
    """Return (value, supported). `value` is the canonical port if known, otherwise the cleaned raw text."""
    if not raw or not raw.strip():
        return None, False
    n = norm(raw)
    for port in known_ports:
        aliases = [norm(a) for a in PORT_ALIASES.get(port, [])] + [norm(port)]
        if n in aliases:
            return port, True
    for port in known_ports:  # whole-word containment, e.g. "delivered to houston terminal"
        if re.search(rf"\b{re.escape(norm(port))}\b", n):
            return port, True
    close = difflib.get_close_matches(n, [norm(p) for p in known_ports], n=1, cutoff=0.85)
    if close:
        return next(p for p in known_ports if norm(p) == close[0]), True
    return " ".join(w.capitalize() for w in re.sub(r"[^A-Za-z0-9 ]", " ", raw).split()), False
