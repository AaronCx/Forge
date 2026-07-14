"""Document chunking service — splits text into overlapping chunks.

A small dependency-free recursive splitter (Phase 8 removed LangChain): it tries
progressively finer separators so chunks break on paragraph, then line, then
sentence, then word boundaries, with a character overlap between chunks.
"""

from __future__ import annotations

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_on(text: str, sep: str) -> list[str]:
    if sep == "":
        return list(text)
    parts = text.split(sep)
    # Re-attach the separator (except the last piece) so joins are lossless-ish.
    return [p + sep for p in parts[:-1]] + parts[-1:] if len(parts) > 1 else parts


def _recursive_split(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if len(text) <= chunk_size or not separators:
        return [text] if text else []
    sep, *rest = separators
    pieces = _split_on(text, sep)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_recursive_split(piece, chunk_size, rest))
        elif len(current) + len(piece) <= chunk_size:
            current += piece
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks using recursive character splitting."""
    if not text:
        return []
    raw = _recursive_split(text, chunk_size, _SEPARATORS)
    if chunk_overlap <= 0 or len(raw) <= 1:
        return [c for c in raw if c]

    # Prepend a tail of the previous chunk for context continuity.
    overlapped: list[str] = []
    for i, chunk in enumerate(raw):
        if i == 0:
            overlapped.append(chunk)
            continue
        tail = raw[i - 1][-chunk_overlap:]
        overlapped.append(tail + chunk)
    return [c for c in overlapped if c]
