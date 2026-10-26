"""命令行入口：支持 local、sdk 和 mcp 三种模式。"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from agent_app.config import Settings, get_settings
from agent_app.local_agent import LocalCustomerServiceAgent
from agent_app.tools import ToolService
from agent_app.tracing import TraceLogger


def build_service(settings: Settings) -> ToolService:
    return ToolService(
        settings.data_dir,
        settings.runtime_dir,
        settings.chunk_size,
        settings.chunk_overlap,
        settings.top_k,
        settings.min_retrieval_score,
    )


def print_local_response(response, show_retrieval: bool = False) -> None:
    print(f"\nAgent：{response.answer}")
    print(f"意图：{response.intent} | 工具：{', '.join(response.tools_used) or '无'} | Trace：{response.trace_id}")
    if show_retrieval and response.retrieval_hits:
        print("\n检索明细：")
        for index, hit in enumerate(response.retrieval_hits, 1):
            print(
                f"  {index}. {hit.source} / {hit.heading} | "
                f"BM25={hit.bm25_score:.3f} Vector={hit.vector_score:.3f} "
                f"Rerank={hit.rerank_score:.3f}"
            )
            print(f"     {hit.content[:160].replace(chr(10), ' ')}")


def local_chat(settings: Settings, question: str | None, show_retrieval: bool) -> None:
    service = build_service(settings)
    agent = LocalCustomerServiceAgent(
        service,
        TraceLogger(settings.runtime_dir / "local_traces.jsonl"),
    )
    if question:
        print_local_response(agent.ask(question), show_retrieval)
        return

    print("本地电商客服 Agent 已启动。输入 exit 退出。")
    print("模拟订单：ORD1001、ORD1002、ORD1003")
    while True:
        user_input = input("\n你：").strip()
        if user_input.lower() in {"exit", "quit", "q"}:
            break
        print_local_response(agent.ask(user_input), show_retrieval)


def approval_prompt(details: str) -> bool:
    print("\n检测到有副作用的工具调用，需要人工审批：")
    print(details)
    return input("是否批准？输入 y 批准，其他输入拒绝：").strip().lower() == "y"


async def _api_chat_loop(runner, question: str | None) -> None:
    if question:
        print("\nAgent：" + await runner.run_turn(question, approval_prompt))
        return
    print("API Agent 已启动。输入 exit 退出。")
    while True:
        user_input = input("\n你：").strip()
        if user_input.lower() in {"exit", "quit", "q"}:
            break
        answer = await runner.run_turn(user_input, approval_prompt)
        print("\nAgent：" + answer)


async def api_chat(settings: Settings, mode: str, question: str | None) -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("sdk/mcp 模式需要 OPENAI_API_KEY；请复制 .env.example 为 .env 后填写。")
    try:
        from agent_app.openai_agents import build_mcp_runner, build_multi_agent_runner
    except ImportError as exc:
        raise RuntimeError("缺少 API 模式依赖，请先运行 pip install -r requirements.txt") from exc

    service = build_service(settings)
    if mode == "sdk":
        await _api_chat_loop(build_multi_agent_runner(service, settings), question)
        return
    server_script = Path(__file__).resolve().parent / "mcp_server.py"
    async with build_mcp_runner(service, settings, server_script) as runner:
        await _api_chat_loop(runner, question)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="电商智能客服 Agentic RAG Demo")
    parser.add_argument("--mode", choices=["local", "sdk", "mcp"], help="运行模式")
    parser.add_argument("--question", help="单次提问；不填写则进入交互模式")
    parser.add_argument("--show-retrieval", action="store_true", help="显示检索分数与片段")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    mode = args.mode or settings.default_mode
    try:
        if mode == "local":
            local_chat(settings, args.question, args.show_retrieval)
        else:
            asyncio.run(api_chat(settings, mode, args.question))
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"启动失败：{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
