"""加载本地 Markdown，保留文件名用于溯源。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    source: str
    text: str


def load_documents(data_dir: Path) -> list[Document]:
    """按文件名排序读取目录中的 .md；忽略空文件，返回文档列表。"""
    if not data_dir.is_dir():
        raise ValueError(f"知识库目录不存在：{data_dir}")
    documents = []
    for path in sorted(data_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        if text.strip():
            documents.append(Document(source=path.name, text=text))
    if not documents:
        raise ValueError("知识库中没有非空 Markdown 文档。")
    return documents
