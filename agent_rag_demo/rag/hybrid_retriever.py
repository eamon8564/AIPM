"""BM25 + 哈希字符向量 + 可解释重排的本地混合检索基线。"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from agent_app.schemas import RetrievalHit

from .chunker import Chunk


ASCII_WORD = re.compile(r"[a-zA-Z0-9@._+-]+")
CHINESE_BLOCK = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """同时提取英文词、中文单字和中文二元词，避免额外分词依赖。"""
    lowered = text.lower()
    tokens = ASCII_WORD.findall(lowered)
    for block in CHINESE_BLOCK.findall(lowered):
        tokens.extend(block)
        tokens.extend(block[i : i + 2] for i in range(len(block) - 1))
    return tokens


def _char_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> list[str]:
    compact = re.sub(r"\s+", "", text.lower())
    result: list[str] = []
    for n in range(min_n, max_n + 1):
        result.extend(compact[i : i + n] for i in range(max(0, len(compact) - n + 1)))
    return result


def _hashed_vector(text: str, dimensions: int = 384) -> list[float]:
    """零依赖向量化：将字符 n-gram 稳定映射到固定维度。"""
    vector = [0.0] * dimensions
    for gram in _char_ngrams(text):
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        index = value % dimensions
        sign = 1.0 if value & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class HybridRetriever:
    """在小型本地知识库上提供可解释、无需联网的混合检索。"""

    def __init__(self, chunks: list[Chunk], bm25_weight: float = 0.55):
        if not chunks:
            raise ValueError("chunks 不能为空")
        self.chunks = chunks
        self.bm25_weight = bm25_weight
        self.vector_weight = 1.0 - bm25_weight
        self.tokenized = [tokenize(f"{c.heading} {c.content}") for c in chunks]
        self.term_frequencies = [Counter(tokens) for tokens in self.tokenized]
        self.doc_lengths = [len(tokens) for tokens in self.tokenized]
        self.avg_doc_length = sum(self.doc_lengths) / max(len(self.doc_lengths), 1)
        self.document_frequency: Counter[str] = Counter()
        for tokens in self.tokenized:
            self.document_frequency.update(set(tokens))
        self.vectors = [_hashed_vector(f"{c.heading} {c.content}") for c in chunks]

    def _bm25(self, query_tokens: list[str], index: int) -> float:
        k1, b = 1.5, 0.75
        score = 0.0
        tf = self.term_frequencies[index]
        length = self.doc_lengths[index]
        total = len(self.chunks)
        for token in query_tokens:
            frequency = tf.get(token, 0)
            if not frequency:
                continue
            df = self.document_frequency.get(token, 0)
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / max(self.avg_doc_length, 1))
            score += idf * frequency * (k1 + 1) / denominator
        return score

    @staticmethod
    def _normalise(values: list[float]) -> list[float]:
        highest = max(values) if values else 0.0
        if highest <= 0:
            return [0.0 for _ in values]
        return [value / highest for value in values]

    def search(self, query: str, top_k: int = 3, min_score: float = 0.08) -> list[RetrievalHit]:
        query_tokens = tokenize(query)
        query_vector = _hashed_vector(query)
        raw_bm25 = [self._bm25(query_tokens, i) for i in range(len(self.chunks))]
        bm25_scores = self._normalise(raw_bm25)
        vector_scores = [max(0.0, _cosine(query_vector, vector)) for vector in self.vectors]

        query_set = set(query_tokens)
        meaningful_query = {token for token in query_set if len(token) > 1}
        results: list[RetrievalHit] = []
        for index, chunk in enumerate(self.chunks):
            coverage = len(query_set.intersection(self.term_frequencies[index])) / max(len(query_set), 1)
            meaningful_overlap = meaningful_query.intersection(self.term_frequencies[index])
            heading_bonus = 0.08 if any(token in chunk.heading.lower() for token in query_set) else 0.0
            hybrid = self.bm25_weight * bm25_scores[index] + self.vector_weight * vector_scores[index]
            rerank = min(1.0, hybrid + 0.18 * coverage + heading_bonus)
            # 只有单字或哈希碰撞命中时不视为充分证据，避免把无关片段当答案。
            if meaningful_query and not meaningful_overlap:
                rerank = min(rerank, 0.05)
            if rerank >= min_score:
                results.append(
                    RetrievalHit(
                        content=chunk.content,
                        source=chunk.source,
                        heading=chunk.heading,
                        score=round(hybrid, 4),
                        bm25_score=round(bm25_scores[index], 4),
                        vector_score=round(vector_scores[index], 4),
                        rerank_score=round(rerank, 4),
                    )
                )
        results.sort(key=lambda hit: hit.rerank_score, reverse=True)
        return results[:top_k]
