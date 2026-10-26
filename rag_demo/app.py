"""CLI 入口：python app.py，或使用 --question 单次提问。"""

import argparse
import json
import sys
from time import perf_counter
from pathlib import Path

from rag.pipeline import RAGPipeline
from models.codex_llm import build_codex_prompt


def show_answer(pipeline: RAGPipeline, question: str, args: argparse.Namespace) -> None:
    if args.backend == "codex" and not args.retrieval_only:
        print("正在检索；证据达到阈值后将调用 Codex，请稍候……", flush=True)
    start = perf_counter()
    response = pipeline.ask(question, args.top_k, args.min_score, args.retrieval_only, args.backend,
                            codex_model=args.codex_model, codex_effort=args.codex_effort)
    elapsed = perf_counter() - start
    print(f"\n问题：{question}\n\n=== 检索结果（候选证据，不是最终答案）===")
    if not response.results:
        print("没有正相似度的片段。")
    for i, result in enumerate(response.results, start=1):
        chunk = result.chunk
        print(f"\n[{i}] {chunk.chunk_id} | 分数={result.score:.4f} | "
              f"来源={chunk.source} | 字符位置=[{chunk.start}, {chunk.end})")
        print(chunk.text)
    if args.show_prompt:
        print("\n=== Prompt 预览（预览不代表已调用 API）===")
        print(json.dumps(response.messages, ensure_ascii=False, indent=2))
        if args.backend == "codex":
            print("\n=== 实际传给 Codex CLI 的文本（不含 CLI 自身内部指令）===")
            print(build_codex_prompt(response.messages))
    print(f"\n=== 运行状态：{response.status} ===\n{response.notice}")
    print(f"本次检索与生成耗时：{elapsed:.2f} 秒（不含启动建索引）")
    if response.answer is not None:
        print(f"\n=== LLM 回答 ===\n{response.answer}")
        print("\n=== 回答中有效编号对应的来源 ===")
        for i, result in response.citations.items():
            print(f"[{i}] {result.chunk.source}（{result.chunk.chunk_id}）")
        if not response.citations:
            print("无有效引用编号。")
        if response.citation_warning:
            print(f"引用提示：{response.citation_warning}")


def main() -> int:
    parser = argparse.ArgumentParser(description="星桥优选：面向 AI PM 学习的轻量 RAG Demo")
    parser.add_argument("--question", "-q", help="单次提问；不传则进入交互模式")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--chunk-size", type=int, default=300, help="每块字符数，默认 300")
    parser.add_argument("--chunk-overlap", type=int, default=60, help="相邻块重叠字符数，默认 60")
    parser.add_argument("--top-k", type=int, default=3, help="最多召回片段数，默认 3")
    parser.add_argument("--min-score", type=float, default=0.08, help="允许生成的最高分下限，默认 0.08")
    parser.add_argument("--show-chunks", action="store_true", help="显示全部切块；不传问题时显示后退出")
    parser.add_argument("--show-prompt", action="store_true", help="显示送给 LLM 的消息内容")
    parser.add_argument("--retrieval-only", action="store_true", help="即使配置了 API 也只运行检索")
    parser.add_argument("--backend", choices=("api", "codex"), default="api",
                        help="生成方式：api 使用环境变量；codex 使用已登录的订阅账号")
    parser.add_argument("--codex-model", help="显式指定 Codex 模型 ID；须是账号可用模型")
    parser.add_argument("--codex-effort", choices=("low", "medium", "high", "xhigh", "max", "ultra"),
                        help="Codex 推理强度，具体可用级别取决于模型")
    parser.add_argument("--show-config", action="store_true", help="显示实验配置；不带问题或 show-chunks 时退出")
    args = parser.parse_args()
    if args.top_k < 1 or not 0 <= args.min_score <= 1:
        parser.error("top-k 必须大于 0；min-score 必须在 0 到 1 之间。")
    if (args.codex_model or args.codex_effort) and args.backend != "codex":
        parser.error("--codex-model / --codex-effort 必须与 --backend codex 一起使用。")
    if args.backend == "codex" or args.show_config:
        print(f"生成后端：{args.backend}；仅检索：{args.retrieval_only}")
        print(f"切块：{args.chunk_size}；重叠：{args.chunk_overlap}；K：{args.top_k}；阈值：{args.min_score}")
        if args.backend == "codex":
            print(f"请求的模型：{args.codex_model or '未指定，由 Codex 决定（未核实实际模型）'}")
            print(f"请求的推理强度：{args.codex_effort or '未指定，由 Codex 决定'}")
            print("个人 config.toml：不加载；沙箱：read-only；每题独立会话。")
        if args.show_config and args.question is None and not args.show_chunks:
            return 0
    try:
        pipeline = RAGPipeline(args.data_dir, args.chunk_size, args.chunk_overlap)
    except (ValueError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
    print(f"知识库：{len(pipeline.documents)} 份文档 / {len(pipeline.chunks)} 个 Chunk。")
    if args.show_chunks:
        for chunk in pipeline.chunks:
            print(f"\n--- {chunk.chunk_id} | [{chunk.start}, {chunk.end}) "
                  f"| {len(chunk.text)} 字符 ---\n{chunk.text}")
        if args.question is None:
            return 0
    if args.question is not None:
        try:
            show_answer(pipeline, args.question, args)
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    print("输入问题开始检索；输入 exit / quit / 退出结束。每次提问独立处理，不保留对话记忆。")
    while True:
        try:
            question = input("\n你的问题 > ").strip()
            if question.lower() in ("exit", "quit", "退出"):
                break
            if not question:
                continue
            show_answer(pipeline, question, args)
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            break
        except ValueError as exc:
            print(f"输入有误：{exc}")
    return 0


if __name__ == "__main__":
    # Windows 在输出被终端工具/文件捕获时可能默认使用本地代码页；统一 UTF-8。
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
