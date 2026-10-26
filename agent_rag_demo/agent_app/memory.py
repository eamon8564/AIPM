"""轻量级会话记忆：保存订单号、历史意图和待确认动作。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import PendingAction


@dataclass
class ConversationMemory:
    last_order_id: str | None = None
    last_intent: str | None = None
    pending_action: PendingAction | None = None
    turns: list[dict[str, str]] = field(default_factory=list)

    def add_turn(self, role: str, content: str) -> None:
        self.turns.append({"role": role, "content": content})
        # 教学 Demo 只保留最近 12 条，避免上下文无限增长。
        self.turns = self.turns[-12:]

    def clear_pending_action(self) -> None:
        self.pending_action = None
