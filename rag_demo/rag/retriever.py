"""拟合知识库向量，使用同一词表转换问题并做余弦相似度排序。"""

from dataclasses import dataclass

from sklearn.metrics.pairwise import cosine_similarity

from models.vectorizer import create_vectorizer
from rag.chunker import Chunk


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("没有可建立索引的 Chunk。")
        self.chunks = chunks
        self.vectorizer = create_vectorizer()
        try:
            # 只在建索引时 fit；问题不能重新 fit，否则词表不一致。
            self.matrix = self.vectorizer.fit_transform([c.text for c in chunks])
        except ValueError as exc:
            raise ValueError("知识库无法提取字符特征，请检查文档内容和切块长度。") from exc

    def search(self, question: str, top_k: int = 3) -> list[SearchResult]:
        """返回最多 K 个正分片段，按相似度降序；零分结果不凑数。"""
        if not question.strip():
            raise ValueError("问题不能为空。")
        if top_k < 1:
            raise ValueError("top_k 必须为正整数。")
        query = self.vectorizer.transform([question])
        scores = cosine_similarity(query, self.matrix).ravel()
        indices = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
        return [
            SearchResult(self.chunks[i], float(scores[i]))
            for i in indices[:top_k]
            if scores[i] > 0
        ]
