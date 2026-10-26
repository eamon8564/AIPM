"""无需 API Key 的确定性 Agent，用于理解规划、工具、记忆与审批。"""

from __future__ import annotations

import re
from typing import Any

from .guardrails import grounded_fallback, validate_user_input
from .memory import ConversationMemory
from .schemas import AgentResponse, PendingAction, RetrievalHit
from .tools import ToolService
from .tracing import TraceLogger


ORDER_PATTERN = re.compile(r"\bORD\d{4,}\b", re.IGNORECASE)


class LocalCustomerServiceAgent:
    def __init__(self, service: ToolService, trace_logger: TraceLogger):
        self.service = service
        self.trace_logger = trace_logger
        self.memory = ConversationMemory()

    def _extract_order_id(self, text: str) -> str | None:
        match = ORDER_PATTERN.search(text)
        if match:
            order_id = match.group(0).upper()
            self.memory.last_order_id = order_id
            return order_id
        return self.memory.last_order_id

    @staticmethod
    def _classify_intent(text: str) -> str:
        if any(word in text for word in ("物流", "快递", "到哪", "送达", "运单")):
            return "logistics"
        if any(word in text for word in ("退货", "退款", "售后", "工单")):
            return "after_sales"
        if any(word in text for word in ("订单", "购买记录", "状态")):
            return "order"
        return "knowledge"

    @staticmethod
    def _best_sentences(hits: list[RetrievalHit], limit: int = 3) -> str:
        sentences: list[str] = []
        for hit in hits[:2]:
            for sentence in re.split(r"(?<=[。！？；])", hit.content):
                cleaned = sentence.strip()
                if cleaned and cleaned not in sentences:
                    sentences.append(cleaned)
                if len(sentences) >= limit:
                    return "".join(sentences)
        return "".join(sentences)

    def _finish(
        self,
        trace_id: str,
        answer: str,
        intent: str,
        tools: list[str],
        citations: list[str] | None = None,
        hits: list[RetrievalHit] | None = None,
        pending_action: PendingAction | None = None,
    ) -> AgentResponse:
        response = AgentResponse(
            answer=answer,
            intent=intent,
            tools_used=tools,
            citations=citations or [],
            retrieval_hits=hits or [],
            trace_id=trace_id,
            pending_action=pending_action,
        )
        self.memory.last_intent = intent
        self.memory.add_turn("assistant", answer)
        self.trace_logger.log(trace_id, "final_response", response.to_dict())
        return response

    def ask(self, question: str) -> AgentResponse:
        trace_id = self.trace_logger.new_trace_id()
        valid, cleaned = validate_user_input(question)
        if not valid:
            return self._finish(trace_id, cleaned, "blocked", [])

        self.memory.add_turn("user", cleaned)
        self.trace_logger.log(trace_id, "user_input", {"question": cleaned})

        if cleaned in {"确认", "确认创建", "同意"} and self.memory.pending_action:
            pending = self.memory.pending_action
            result = self.service.create_after_sales_ticket(**pending.arguments)
            self.memory.clear_pending_action()
            self.trace_logger.log(trace_id, "tool_result", {"tool": pending.action, "result": result})
            answer = (
                f"已创建售后工单 {result['ticket_id']}，状态为待人工审核。"
                if result.get("created")
                else result.get("message", "工单创建失败。")
            )
            return self._finish(trace_id, answer, "approval", [pending.action])

        if cleaned in {"取消", "不同意", "拒绝"} and self.memory.pending_action:
            self.memory.clear_pending_action()
            return self._finish(trace_id, "已取消待执行的售后工单操作。", "approval", [])

        intent = self._classify_intent(cleaned)
        order_id = self._extract_order_id(cleaned)
        self.trace_logger.log(trace_id, "plan", {"intent": intent, "order_id": order_id})

        if intent == "order":
            if not order_id:
                return self._finish(trace_id, "请提供模拟订单号，例如 ORD1001。", intent, [])
            result = self.service.query_order(order_id)
            self.trace_logger.log(trace_id, "tool_result", {"tool": "query_order", "result": result})
            if not result.get("found"):
                return self._finish(trace_id, result["message"], intent, ["query_order"])
            answer = f"订单 {order_id}：{result['product']}，金额 {result['amount']} 元，当前状态为{result['status']}。"
            return self._finish(trace_id, answer, intent, ["query_order"])

        if intent == "logistics":
            if not order_id:
                return self._finish(trace_id, "请先提供需要查询的模拟订单号。", intent, [])
            result = self.service.track_logistics(order_id)
            self.trace_logger.log(trace_id, "tool_result", {"tool": "track_logistics", "result": result})
            if not result.get("found"):
                return self._finish(trace_id, result["message"], intent, ["track_logistics"])
            answer = f"订单 {order_id} 由{result.get('carrier') or '承运商'}配送，最新状态：{result.get('latest_event') or result['status']}"
            if result.get("estimated_delivery"):
                answer += f"，预计送达时间为 {result['estimated_delivery']}"
            return self._finish(trace_id, answer + "。", intent, ["track_logistics"])

        if intent == "after_sales" and order_id:
            result = self.service.check_return_eligibility(order_id)
            self.trace_logger.log(trace_id, "tool_result", {"tool": "check_return_eligibility", "result": result})
            answer = f"订单 {order_id}：{result.get('reason', result.get('message', '无法判断'))}"
            wants_action = any(word in cleaned for word in ("申请", "创建", "办理", "提交"))
            pending = None
            if result.get("eligible") and wants_action:
                pending = PendingAction(
                    action="create_after_sales_ticket",
                    arguments={"order_id": order_id, "reason": "用户申请退货退款"},
                    summary=f"为订单 {order_id} 创建退货退款工单",
                )
                self.memory.pending_action = pending
                answer += " 如需创建售后工单，请回复“确认”；回复“取消”则不执行。"
            return self._finish(
                trace_id,
                answer,
                intent,
                ["check_return_eligibility"],
                pending_action=pending,
            )

        result: dict[str, Any] = self.service.search_knowledge(cleaned)
        self.trace_logger.log(trace_id, "tool_result", {"tool": "search_knowledge", "result": result})
        hits = [RetrievalHit(**item) for item in result["results"]]
        if not result["enough_evidence"] or not hits:
            return self._finish(trace_id, grounded_fallback(), intent, ["search_knowledge"])
        citations = list(dict.fromkeys(hit.source for hit in hits))
        answer = self._best_sentences(hits)
        if not answer:
            answer = grounded_fallback()
        answer += "\n来源：" + "、".join(citations)
        return self._finish(trace_id, answer, intent, ["search_knowledge"], citations, hits)
