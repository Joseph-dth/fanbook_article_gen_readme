"""HTML stripping + sliding-window chunking for transcript text."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class Chunk:
    text: str
    char_start: int
    char_end: int


def strip_html(html_or_text: str | None) -> str:
    if not html_or_text:
        return ""
    if "<" not in html_or_text:
        return html_or_text.strip()
    soup = BeautifulSoup(html_or_text, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def chunk_text(text: str, size: int = 500, overlap: int = 100) -> Iterator[Chunk]:
    """Sliding-window chunks measured in characters (CJK-friendly).

    The last chunk is yielded even if shorter than `size`. Empty input yields
    nothing.
    """
    if not text:
        return
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be in [0, size)")
    step = size - overlap
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        yield Chunk(text=text[start:end], char_start=start, char_end=end)
        if end == n:
            return
        start += step
