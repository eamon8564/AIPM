"""离线验证 Codex 适配，不使用订阅额度。"""

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from models.codex_llm import build_codex_command, build_codex_prompt, generate_codex, subscription_env
from models.llm import LLMError
from rag.pipeline import RAGPipeline


def result(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def events(*items):
    return "\n".join(json.dumps(item) for item in items)


class CodexTests(unittest.TestCase):
    def test_explicit_model_and_effort(self):
        command = build_codex_command("codex.exe", "D:/temp folder", "test-model", "medium")
        self.assertEqual(command[command.index("--model") + 1], "test-model")
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertEqual(command[-1], "-")
        default = build_codex_command("codex.exe", "D:/temp")
        self.assertNotIn("--model", default)
        self.assertNotIn("-c", default)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "fake", "CODEX_API_KEY": "fake"})
    def test_api_keys_excluded(self):
        self.assertNotIn("OPENAI_API_KEY", subscription_env())
        self.assertNotIn("CODEX_API_KEY", subscription_env())

    @patch("models.codex_llm.find_codex", return_value="codex.exe")
    @patch("models.codex_llm.subprocess.run")
    def test_logged_in_generation(self, run, find):
        run.side_effect = [result(stderr="Logged in using ChatGPT"), result(events(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "签收次日起 7 天。[1]"}},
            {"type": "turn.completed"},
        ))]
        messages = [{"role": "user", "content": "退货？"}]
        self.assertEqual(generate_codex(messages, model="test-model", effort="low"), "签收次日起 7 天。[1]")
        call = run.call_args
        self.assertIn("--ignore-user-config", call.args[0])
        self.assertIn("read-only", call.args[0])
        self.assertEqual(call.args[0][-1], "-")
        self.assertIn("退货？", call.kwargs["input"])
        self.assertEqual(call.kwargs["input"], build_codex_prompt(messages))
        self.assertIn("test-model", call.args[0])
        self.assertIn('model_reasoning_effort="low"', call.args[0])

    @patch("models.codex_llm.find_codex", return_value="codex.exe")
    @patch("models.codex_llm.subprocess.run")
    def test_missing_login_or_api_login_does_not_generate(self, run, find):
        for status in [result(code=1), result(stderr="Logged in using an API key")]:
            run.reset_mock()
            run.return_value = status
            with self.assertRaisesRegex(LLMError, "订阅登录"):
                generate_codex([])
            self.assertEqual(run.call_count, 1)

    @patch("models.codex_llm.find_codex", return_value="codex.exe")
    @patch("models.codex_llm.subprocess.run")
    def test_reject_tool_use_and_incomplete_events(self, run, find):
        responses = [
            result(events({"type": "item.completed", "item": {"type": "command_execution"}})),
            result(events({"type": "turn.failed"})),
            result(events({"type": "item.completed", "item": {"type": "agent_message", "text": "未完成"}})),
            result("not JSON"), result(code=1),
        ]
        for response in responses:
            run.side_effect = [result(stderr="Logged in using ChatGPT"), response]
            with self.assertRaises(LLMError):
                generate_codex([])

    @patch("models.codex_llm.find_codex", return_value="codex.exe")
    @patch("models.codex_llm.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 20))
    def test_timeout(self, run, find):
        with self.assertRaisesRegex(LLMError, "超时"):
            generate_codex([])

    @patch.dict("os.environ", {}, clear=True)
    @patch("rag.pipeline.generate_codex", return_value="签收次日起 7 个自然日。[1]")
    @patch("rag.pipeline.generate")
    def test_pipeline_routes_without_api_key(self, api, codex):
        pipeline = RAGPipeline(Path(__file__).resolve().parents[1] / "data")
        response = pipeline.ask("购买商品后多少天内可以申请退货？", backend="codex",
                                codex_model="test-model", codex_effort="medium")
        self.assertEqual(response.status, "generated")
        self.assertEqual(response.citations[1].chunk.source, "returns.md")
        api.assert_not_called()
        codex.assert_called_once()
        self.assertEqual(codex.call_args.kwargs, {"model": "test-model", "effort": "medium"})
        codex.reset_mock()
        pipeline.ask("退货", backend="codex", retrieval_only=True)
        pipeline.ask("zxqv987654321", backend="codex")
        codex.assert_not_called()
        codex.side_effect = LLMError("未登录")
        failed = pipeline.ask("退货", backend="codex")
        self.assertEqual(failed.status, "llm_error")
        self.assertTrue(failed.results)


if __name__ == "__main__":
    unittest.main()
