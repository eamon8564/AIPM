"""Agent、工具和检索模块共享的数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RetrievalHit:
    content: str
    source: str
    heading: str
    score: float
    bm25_score: float
    vector_score: float
    rerank_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PendingAction:
    action: str
    arguments: dict[str, Any]
    summary: str


@dataclass
class AgentResponse:
    answer: str
    intent: str
    tools_used: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    retrieval_hits: list[RetrievalHit] = field(default_factory=list)
    trace_id: str = ""
    pending_action: PendingAction | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result
