"""按标题和固定长度切块，保留来源与标题信息。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .loader import Document


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    heading: str
    content: str


def _split_sections(text: str) -> list[tuple[str, str]]:
    heading = "正文"
    buffer: list[str] = []
    sections: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if match:
            if buffer:
                sections.append((heading, "\n".join(buffer).strip()))
                buffer = []
            heading = match.group(1).strip()
        else:
            buffer.append(line)
    if buffer:
        sections.append((heading, "\n".join(buffer).strip()))
    return [(h, body) for h, body in sections if body]


def chunk_documents(
    documents: list[Document], chunk_size: int = 360, chunk_overlap: int = 60
) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap 必须满足 0 <= overlap < chunk_size")

    chunks: list[Chunk] = []
    for document in documents:
        index = 0
        for heading, section_text in _split_sections(document.text):
            start = 0
            while start < len(section_text):
                end = min(start + chunk_size, len(section_text))
                content = section_text[start:end].strip()
                if content:
                    chunks.append(
                        Chunk(
                            chunk_id=f"{document.source}:{index}",
                            source=document.source,
                            heading=heading,
                            content=content,
                        )
                    )
                    index += 1
                if end >= len(section_text):
                    break
                start = end - chunk_overlap
    return chunks
