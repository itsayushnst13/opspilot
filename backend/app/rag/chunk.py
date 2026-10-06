"""Split parsed segments into overlapping, citation-friendly chunks."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..docproc.parsers import ParsedDocument

PRODUCT_CODE_RE = re.compile(r"CHEM-X\d{2}", re.IGNORECASE)


@dataclass
class Chunk:
    index: int
    content: str
    locator: str
    product_codes: list[str]


def extract_product_codes(text: str) -> list[str]:
    return sorted({m.upper() for m in PRODUCT_CODE_RE.findall(text)})


def chunk_document(doc: ParsedDocument, max_chars: int = 900) -> list[Chunk]:
    """Pack lines (or CSV rows) into chunks of ~max_chars, overlapping by one line."""
    units: list[tuple[str, str]] = []
    for seg in doc.segments:
        for line in seg.text.split("\n"):
            line = line.strip()
            if line:
                # break pathological very long lines
                while len(line) > max_chars:
                    units.append((line[:max_chars], seg.locator))
                    line = line[max_chars:]
                units.append((line, seg.locator))

    chunks: list[Chunk] = []
    buf: list[tuple[str, str]] = []
    size = 0

    def flush() -> None:
        if not buf:
            return
        text = "\n".join(t for t, _ in buf)
        locs = [loc for _, loc in buf]
        locator = locs[0] if locs[0] == locs[-1] else f"{locs[0]} .. {locs[-1]}"
        chunks.append(Chunk(len(chunks), text, locator, extract_product_codes(text)))

    for unit in units:
        if size + len(unit[0]) > max_chars and buf:
            flush()
            buf = [buf[-1]]  # one-line overlap
            size = len(buf[0][0])
        buf.append(unit)
        size += len(unit[0]) + 1
    # avoid emitting a final chunk that is only the overlap line
    if len(buf) > 1 or not chunks:
        flush()
    return chunks
