"""固定字符窗口切块，不跨文件；位置为从 0 开始的 [start, end)。"""

from dataclasses import dataclass

from rag.loader import Document


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    text: str
    start: int
    end: int


def chunk_documents(
    documents: list[Document], chunk_size: int = 300, chunk_overlap: int = 60
) -> list[Chunk]:
    """输入文档和字符数参数，输出包含原文位置及来源的 Chunk。"""
    if chunk_size < 2:
        raise ValueError("chunk_size 必须至少为 2（字符二元组检索需要）。")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap 必须满足 0 <= overlap < chunk_size。")
    chunks = []
    step = chunk_size - chunk_overlap
    for doc in documents:
        for index, start in enumerate(range(0, len(doc.text), step), start=1):
            end = min(start + chunk_size, len(doc.text))
            text = doc.text[start:end]
            if text.strip():
                chunks.append(Chunk(f"{doc.source}#{index}", doc.source, text, start, end))
            # 最后一块已覆盖结尾时停止，不再制造只含重复尾部的小块。
            if end == len(doc.text):
                break
    return chunks
