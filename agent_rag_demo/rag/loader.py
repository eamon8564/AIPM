"""读取本地 Markdown 知识库。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    source: str
    text: str


def load_markdown_documents(data_dir: Path) -> list[Document]:
    documents: list[Document] = []
    for path in sorted(data_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            documents.append(Document(source=path.name, text=text))
    if not documents:
        raise FileNotFoundError(f"未在 {data_dir} 找到 Markdown 知识文档")
    return documents
