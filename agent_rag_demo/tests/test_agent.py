from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_app.config import get_settings
from agent_app.local_agent import LocalCustomerServiceAgent
from agent_app.tools import ToolService
from agent_app.tracing import TraceLogger


class AgentDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()
        self.temp_dir = tempfile.TemporaryDirectory()
        runtime = Path(self.temp_dir.name)
        self.service = ToolService(
            self.settings.data_dir,
            runtime,
            self.settings.chunk_size,
            self.settings.chunk_overlap,
            self.settings.top_k,
            self.settings.min_retrieval_score,
        )
        self.trace_logger = TraceLogger(runtime / "trace.jsonl")
        self.agent = LocalCustomerServiceAgent(self.service, self.trace_logger)

    def tearDown(self) -> None:
        self.trace_logger.close()
        self.temp_dir.cleanup()

    def test_product_retrieval(self) -> None:
        response = self.agent.ask("轻风蓝牙耳机续航多久？")
        self.assertEqual(response.intent, "knowledge")
        self.assertIn("products.md", response.citations)
        self.assertIn("24 小时", response.answer)

    def test_order_tool(self) -> None:
        response = self.agent.ask("查询订单 ORD1001")
        self.assertIn("query_order", response.tools_used)
        self.assertIn("已发货", response.answer)

    def test_memory_reuses_order_id(self) -> None:
        self.agent.ask("查询订单 ORD1001")
        response = self.agent.ask("物流到哪里了？")
        self.assertIn("track_logistics", response.tools_used)
        self.assertIn("武汉转运中心", response.answer)

    def test_human_approval_before_ticket(self) -> None:
        draft = self.agent.ask("为 ORD1002 申请退货")
        self.assertIsNotNone(draft.pending_action)
        self.assertFalse(self.service.ticket_path.exists())
        confirmed = self.agent.ask("确认")
        self.assertIn("已创建售后工单", confirmed.answer)
        self.assertTrue(self.service.ticket_path.exists())

    def test_customised_product_is_not_eligible(self) -> None:
        response = self.agent.ask("ORD1003 可以退货吗？")
        self.assertIn("定制商品", response.answer)
        self.assertIsNone(response.pending_action)

    def test_long_input_guardrail(self) -> None:
        response = self.agent.ask("问" * 900)
        self.assertEqual(response.intent, "blocked")
        self.assertIn("问题过长", response.answer)


if __name__ == "__main__":
    unittest.main()
