"""运行本地 Agent 评测集，不调用任何外部 API。"""

from __future__ import annotations

import json

from agent_app.config import get_settings
from agent_app.local_agent import LocalCustomerServiceAgent
from agent_app.tools import ToolService
from agent_app.tracing import TraceLogger


def main() -> None:
    settings = get_settings()
    cases = json.loads((settings.project_root / "evaluation" / "test_cases.json").read_text(encoding="utf-8"))
    service = ToolService(
        settings.data_dir,
        settings.runtime_dir,
        settings.chunk_size,
        settings.chunk_overlap,
        settings.top_k,
        settings.min_retrieval_score,
    )
    trace_logger = TraceLogger(settings.runtime_dir / "eval_traces.jsonl")
    passed = 0
    for case in cases:
        agent = LocalCustomerServiceAgent(service, trace_logger)
        response = agent.ask(case["question"])
        checks = [
            response.intent == case["expected_intent"],
            case["expected_tool"] in response.tools_used,
            all(text in response.answer for text in case.get("must_contain", [])),
        ]
        if case.get("expected_source"):
            checks.append(case["expected_source"] in response.citations)
        if case.get("expect_pending_action"):
            checks.append(response.pending_action is not None)
        ok = all(checks)
        passed += int(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {case['id']} {case['question']}")
        if not ok:
            print("  回答：", response.answer)
            print("  意图/工具/来源：", response.intent, response.tools_used, response.citations)
    print(f"\n通过：{passed}/{len(cases)}，准确率：{passed / len(cases):.1%}")
    raise SystemExit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()
