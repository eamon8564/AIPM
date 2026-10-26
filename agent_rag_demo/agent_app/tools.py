"""电商客服 Agent 可调用的业务工具。数据均为本地模拟信息。"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from rag.chunker import chunk_documents
from rag.hybrid_retriever import HybridRetriever
from rag.loader import load_markdown_documents


class ToolService:
    def __init__(
        self,
        data_dir: Path,
        runtime_dir: Path,
        chunk_size: int = 360,
        chunk_overlap: int = 60,
        top_k: int = 3,
        min_score: float = 0.08,
    ):
        self.data_dir = data_dir
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.top_k = top_k
        self.min_score = min_score
        documents = load_markdown_documents(data_dir)
        chunks = chunk_documents(documents, chunk_size, chunk_overlap)
        self.retriever = HybridRetriever(chunks)
        raw_orders = json.loads((data_dir / "orders.json").read_text(encoding="utf-8"))
        self.snapshot_date = date.fromisoformat(raw_orders["snapshot_date"])
        self.orders = {item["order_id"].upper(): item for item in raw_orders["orders"]}
        self.ticket_path = runtime_dir / "tickets.jsonl"

    def search_knowledge(self, query: str, top_k: int | None = None) -> dict[str, Any]:
        hits = self.retriever.search(query, top_k or self.top_k, self.min_score)
        return {
            "query": query,
            "results": [hit.to_dict() for hit in hits],
            "enough_evidence": bool(hits and hits[0].rerank_score >= self.min_score),
        }

    def query_order(self, order_id: str) -> dict[str, Any]:
        order = self.orders.get(order_id.upper())
        if not order:
            return {"found": False, "order_id": order_id.upper(), "message": "未找到该模拟订单。"}
        return {
            "found": True,
            "order_id": order["order_id"],
            "product": order["product"],
            "amount": order["amount"],
            "status": order["status"],
            "customised": order.get("customised", False),
        }

    def track_logistics(self, order_id: str) -> dict[str, Any]:
        order = self.orders.get(order_id.upper())
        if not order:
            return {"found": False, "order_id": order_id.upper(), "message": "未找到该模拟订单。"}
        logistics = order.get("logistics") or {}
        return {
            "found": True,
            "order_id": order["order_id"],
            "status": order["status"],
            "carrier": logistics.get("carrier"),
            "tracking_no": logistics.get("tracking_no"),
            "latest_event": logistics.get("latest_event"),
            "estimated_delivery": logistics.get("estimated_delivery"),
        }

    def check_return_eligibility(self, order_id: str) -> dict[str, Any]:
        order = self.orders.get(order_id.upper())
        if not order:
            return {"found": False, "eligible": False, "message": "未找到该模拟订单。"}
        if order["status"] != "已签收":
            return {
                "found": True,
                "eligible": False,
                "order_id": order["order_id"],
                "reason": "订单尚未签收，暂不进入签收后退货期限判断。",
            }
        delivered_at = date.fromisoformat(order["delivered_at"])
        deadline = delivered_at + timedelta(days=7)
        if order.get("customised"):
            return {
                "found": True,
                "eligible": False,
                "order_id": order["order_id"],
                "deadline": deadline.isoformat(),
                "reason": "该订单为定制商品，不支持无理由退货；质量问题需人工核实。",
            }
        eligible = self.snapshot_date <= deadline
        return {
            "found": True,
            "eligible": eligible,
            "order_id": order["order_id"],
            "snapshot_date": self.snapshot_date.isoformat(),
            "delivered_at": delivered_at.isoformat(),
            "deadline": deadline.isoformat(),
            "reason": "仍在签收次日起 7 个自然日内。" if eligible else "已超过无理由退货期限。",
        }

    def create_after_sales_ticket(self, order_id: str, reason: str) -> dict[str, Any]:
        """有副作用的工具：只应在人类明确确认后调用。"""
        order = self.orders.get(order_id.upper())
        if not order:
            return {"created": False, "message": "订单不存在，未创建工单。"}
        ticket_id = f"AS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        record = {
            "ticket_id": ticket_id,
            "order_id": order["order_id"],
            "reason": reason,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "待人工审核",
        }
        with self.ticket_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"created": True, **record}
