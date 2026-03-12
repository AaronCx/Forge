"""Document chunking service — splits text into overlapping chunks."""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks using recursive character splitting."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)
