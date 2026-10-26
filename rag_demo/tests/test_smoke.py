"""最小离线回归：真实 TF-IDF + 模拟 API 响应，不消耗接口额度。"""

import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from models.llm import LLMConfig, LLMError, generate
from rag.chunker import chunk_documents
from rag.loader import Document, load_documents
from rag.pipeline import RAGPipeline


ROOT = Path(__file__).resolve().parents[1]
CONFIG = LLMConfig("test-key-not-real", "https://example.invalid/v1", "test-model")
ENV = {"LLM_API_KEY": CONFIG.api_key, "LLM_BASE_URL": CONFIG.base_url, "LLM_MODEL": CONFIG.model}


def api_response(content: str) -> io.BytesIO:
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = RAGPipeline(ROOT / "data")

    def test_load_and_empty_knowledge_base(self):
        self.assertEqual(len(self.pipeline.documents), 4)
        with TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "empty.md").write_text(" \n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_documents(path)
            (path / "bom.md").write_text("中文知识", encoding="utf-8-sig")
            self.assertEqual(load_documents(path)[0].text, "中文知识")

    def test_chunk_coverage_overlap_and_end(self):
        original = "甲乙丙丁戊己庚辛壬癸子丑"
        chunks = chunk_documents([Document("test.md", original)], 5, 2)
        self.assertEqual([(c.start, c.end) for c in chunks], [(0, 5), (3, 8), (6, 11), (9, 12)])
        for chunk in chunks:
            self.assertEqual(chunk.text, original[chunk.start:chunk.end])
        for previous, current in zip(chunks, chunks[1:]):
            self.assertEqual(previous.text[-2:], current.text[:2])
        exact = chunk_documents([Document("exact.md", "12345678")], 5, 2)
        self.assertEqual(len(exact), 2)

    def test_invalid_chunk_parameters(self):
        for size, overlap in [(0, 0), (1, 0), (10, -1), (10, 10), (10, 11)]:
            with self.subTest(size=size, overlap=overlap), self.assertRaises(ValueError):
                chunk_documents(self.pipeline.documents, size, overlap)

    def test_retrieval_sources_and_evidence(self):
        cases = json.loads((ROOT / "evaluation" / "test_cases.json").read_text(encoding="utf-8"))
        # 核对召回的片段是否真的包含答案关键点，而不只是文件名相同。
        evidence = {
            "Q1": ["签收次日起 7 个自然日", "不从付款日计算"],
            "Q2": ["6 小时", "24 小时", "50%"],
            "Q3": ["15 元", "99 元"],
            "Q4": ["2 个工作日", "1～3 个工作日"],
            "Q5": ["99 元", "365 天", "不自动续费"],
            "Q6": ["48 小时", "2～5 天"],
            "Q7": ["不能放入微波炉"],
        }
        for case in cases:
            if case["expected_source"] is None:
                continue  # 无答案题应人工评估拒答，不能用来源命中代替。
            with self.subTest(case=case["id"]):
                hits = self.pipeline.retriever.search(case["question"])
                self.assertIn(case["expected_source"], [h.chunk.source for h in hits])
                context = "\n".join(h.chunk.text for h in hits)
                for fact in evidence[case["id"]]:
                    self.assertIn(fact, context)
                scores = [h.score for h in hits]
                self.assertEqual(scores, sorted(scores, reverse=True))
                self.assertTrue(all(0 < score <= 1.000001 for score in scores))
                self.assertLessEqual(len(hits), 3)

    def test_top_k_and_invalid_question(self):
        self.assertEqual(len(self.pipeline.retriever.search("退货", 1)), 1)
        self.assertLessEqual(len(self.pipeline.retriever.search("退货", 100)), len(self.pipeline.chunks))
        with self.assertRaises(ValueError):
            self.pipeline.retriever.search("  ")
        with self.assertRaises(ValueError):
            self.pipeline.retriever.search("退货", 0)
        with self.assertRaises(ValueError):
            self.pipeline.ask("退货", min_score=float("nan"))

    @patch.dict("os.environ", {}, clear=True)
    @patch("models.llm.request.urlopen")
    def test_no_key_never_calls_api(self, urlopen):
        response = self.pipeline.ask("购买商品后多少天内可以申请退货？")
        self.assertEqual(response.status, "retrieval_only")
        self.assertIsNone(response.answer)
        self.assertTrue(response.results)
        self.assertIn("LLM_API_KEY", response.notice)
        urlopen.assert_not_called()

    @patch.dict("os.environ", ENV, clear=True)
    @patch("models.llm.request.urlopen")
    def test_forced_retrieval_only(self, urlopen):
        response = self.pipeline.ask("申请退货", retrieval_only=True)
        self.assertEqual(response.status, "retrieval_only")
        urlopen.assert_not_called()

    @patch.dict("os.environ", ENV, clear=True)
    @patch("models.llm.request.urlopen")
    def test_no_overlap_and_high_threshold_skip_api(self, urlopen):
        for question, threshold in [("zxqv987654321", 0.08), ("退货", 1.0)]:
            response = self.pipeline.ask(question, min_score=threshold)
            self.assertEqual(response.status, "no_evidence")
            self.assertIsNone(response.answer)
        urlopen.assert_not_called()

    @patch.dict("os.environ", ENV, clear=True)
    @patch("models.llm.request.urlopen")
    def test_generation_payload_and_citation_mapping(self, urlopen):
        urlopen.return_value = api_response("签收次日起 7 个自然日内可申请无理由退货。[1]")
        response = self.pipeline.ask("购买商品后多少天内可以申请退货？")
        self.assertEqual(response.status, "generated")
        self.assertEqual(response.citations[1].chunk.source, "returns.md")
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key-not-real")
        payload = json.loads(req.data)
        self.assertEqual(payload["model"], "test-model")
        context = json.loads(payload["messages"][1]["content"])
        self.assertEqual(context["knowledge_chunks"][0]["citation"], "[1]")
        self.assertIn("无法确认", payload["messages"][0]["content"])

    @patch.dict("os.environ", ENV, clear=True)
    @patch("models.llm.request.urlopen")
    def test_unknown_question_prompt_and_mock_refusal(self, urlopen):
        urlopen.return_value = api_response("根据现有知识库无法确认免费刻字权益，请联系人工客服。")
        response = self.pipeline.ask("金卡会员购买晨光保温杯可以免费刻字吗？")
        # 验证程序能传递拒答，不代表真实模型已经通过拒答评测。
        self.assertTrue(response.results)
        self.assertIn("无法确认", response.answer)
        self.assertFalse(response.citations)

    @patch.dict("os.environ", ENV, clear=True)
    @patch("models.llm.request.urlopen")
    def test_invalid_citation_is_not_a_source(self, urlopen):
        urlopen.return_value = api_response("错误示例。[99]")
        response = self.pipeline.ask("申请退货")
        self.assertFalse(response.citations)
        self.assertIn("不存在", response.citation_warning)

    @patch.dict("os.environ", ENV, clear=True)
    @patch("models.llm.request.urlopen")
    def test_api_failure_preserves_retrieval(self, urlopen):
        urlopen.side_effect = HTTPError(CONFIG.base_url, 401, "private server body", {}, None)
        response = self.pipeline.ask("申请退货")
        self.assertEqual(response.status, "llm_error")
        self.assertTrue(response.results)
        self.assertIsNone(response.answer)
        self.assertIn("401", response.notice)
        self.assertNotIn(CONFIG.api_key, response.notice)
        self.assertNotIn("private server body", response.notice)

    @patch("models.llm.request.urlopen")
    def test_malformed_responses_and_network_errors(self, urlopen):
        for body in [b"not json", b"{}", b'{"choices": []}', b"null"]:
            urlopen.return_value = io.BytesIO(body)
            with self.subTest(body=body), self.assertRaises(LLMError):
                generate([], CONFIG)
        urlopen.return_value = api_response(" ")
        with self.assertRaises(LLMError):
            generate([], CONFIG)
        for failure in [URLError("offline"), TimeoutError()]:
            urlopen.side_effect = failure
            with self.assertRaises(LLMError):
                generate([], CONFIG)


if __name__ == "__main__":
    unittest.main()
