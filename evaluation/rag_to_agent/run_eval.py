"""Offline reproducible evaluation of retrieval and the deterministic local Agent.

The original RAG dependency (scikit-learn) is unavailable in the bundled
runtime, so R0 uses the same character 2-4 gram, smoothed TF-IDF and cosine
formulas in standard Python. This is a mathematical reproduction, not a run of
the original RAGPipeline or its optional LLM.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KB = HERE / "data" / "knowledge_base"
DATA = HERE / "data"


def old_chunks(size: int = 300, overlap: int = 60) -> list[dict]:
    chunks = []
    for path in sorted(KB.glob("*.md")):
        body = path.read_text(encoding="utf-8-sig")
        step = size - overlap
        for start in range(0, len(body), step):
            end = min(start + size, len(body))
            part = body[start:end]
            if part.strip():
                chunks.append({"source": path.name, "text": part, "start": start, "end": end})
            if end == len(body):
                break
    return chunks


def grams(text: str) -> Counter[str]:
    text = re.sub(r"\s\s+", " ", text.lower())
    return Counter(text[i : i + n] for n in (2, 3, 4) for i in range(max(0, len(text) - n + 1)))


class OriginalTfidf:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        counts = [grams(c["text"]) for c in chunks]
        df: Counter[str] = Counter()
        for count in counts:
            df.update(count.keys())
        self.idf = {term: math.log((1 + len(counts)) / (1 + frequency)) + 1 for term, frequency in df.items()}
        self.vectors = [self._vector(count) for count in counts]

    def _vector(self, count: Counter[str]) -> dict[str, float]:
        weighted = {term: freq * self.idf[term] for term, freq in count.items() if term in self.idf}
        norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
        return {term: value / norm for term, value in weighted.items()}

    def search(self, question: str, top_k: int = 3) -> list[dict]:
        query = self._vector(grams(question))
        scores = [sum(weight * vector.get(term, 0) for term, weight in query.items()) for vector in self.vectors]
        ranks = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [
            {"source": self.chunks[i]["source"], "score": round(scores[i], 6), "start": self.chunks[i]["start"], "text": self.chunks[i]["text"]}
            for i in ranks[:top_k] if scores[i] > 0
        ]


def summarize(rows: list[dict]) -> dict:
    results = defaultdict(lambda: {"n": 0, "r0_source_hit": 0, "r1_source_hit": 0, "r0_evidence_hit": 0, "r1_evidence_hit": 0, "r0_evidence_top1": 0, "r0_heading_evidence_top1": 0, "r1_evidence_top1": 0, "agent_checks": 0})
    for row in rows:
        key = f"{row['split']}/{row['category']}"
        bucket = results[key]
        bucket["n"] += 1
        if row["category"] == "knowledge":
            bucket["r0_source_hit"] += int(row["r0_hit_at_3"])
            bucket["r1_source_hit"] += int(row["r1_hit_at_3"])
            bucket["r0_evidence_hit"] += int(row["r0_evidence_hit_at_3"])
            bucket["r1_evidence_hit"] += int(row["r1_evidence_hit_at_3"])
            bucket["r0_evidence_top1"] += int(row["r0_evidence_top1"])
            bucket["r0_heading_evidence_top1"] += int(row["r0_heading_evidence_top1"])
            bucket["r1_evidence_top1"] += int(row["r1_evidence_top1"])
        bucket["agent_checks"] += int(row["agent_rule_check_pass"])
    return dict(results)


def main() -> None:
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    # Only Agent's native code is imported; importing RAGPipeline would require
    # scikit-learn and an API key for the generation stage.
    sys.path.insert(0, str(ROOT / "agent_rag_demo"))
    from agent_app.local_agent import LocalCustomerServiceAgent
    from agent_app.tools import ToolService
    from agent_app.tracing import TraceLogger

    runtime = HERE / "runtime"
    runtime.mkdir(exist_ok=True)
    for name in ("eval_traces.jsonl", "tickets.jsonl"):
        path = runtime / name
        if path.exists():
            path.unlink()
    trace = TraceLogger(runtime / "eval_traces.jsonl")
    service = ToolService(KB, runtime, 360, 60, 3, 0.08)
    r0 = OriginalTfidf(old_chunks())
    heading_chunks = [
        {"source": c.source, "text": f"{c.heading} {c.content}", "start": 0}
        for c in service.retriever.chunks
    ]
    r0_heading = OriginalTfidf(heading_chunks)
    rows = []
    for case in cases:
        agent = LocalCustomerServiceAgent(service, trace)
        if case.get("context"):
            agent.ask(case["context"])
        ticket_before = service.ticket_path.read_text(encoding="utf-8") if service.ticket_path.exists() else ""
        response = agent.ask(case["question"])
        ticket_after = service.ticket_path.read_text(encoding="utf-8") if service.ticket_path.exists() else ""
        category = case["category"]
        checks = {}
        if category == "knowledge":
            checks = {
                "expected_phrase": case["expected_text"] in response.answer,
                "source_cited": case["expected_source"] in response.citations,
            }
        elif category in {"order_logistics", "multi_turn", "after_sales"}:
            checks = {
                "expected_phrase": case["expected_text"] in response.answer,
                "expected_tool": case["expected_tool"] in response.tools_used,
            }
            if "expect_pending" in case:
                checks["pending_action"] = bool(response.pending_action) == case["expect_pending"]
        elif case["subtype"] == "unknown":
            checks = {"appropriate_abstention": case["expected_text"] in response.answer}
        elif case["subtype"] == "missing_order":
            checks = {"asks_for_order_id": case["expected_text"] in response.answer}
        elif case["subtype"] == "no_approval":
            checks = {
                "asks_confirmation": case["expected_text"] in response.answer,
                "pending_action": bool(response.pending_action),
                "no_ticket_without_confirmation": ticket_before == ticket_after,
            }
        elif case["subtype"] == "unauthorized":
            checks = {
                "does_not_disclose_status": case["forbidden_text"] not in response.answer,
                "does_not_query_order": "query_order" not in response.tools_used,
            }

        r0_hits = r0.search(case["question"]) if category == "knowledge" else []
        r0_heading_hits = r0_heading.search(case["question"]) if category == "knowledge" else []
        r1_hits = service.search_knowledge(case["question"])["results"] if category == "knowledge" else []
        row = {
            "id": case["id"], "split": case["split"], "category": category,
            "subtype": case.get("subtype"), "question": case["question"],
            "context": case.get("context"), "expected_text": case.get("expected_text"),
            "expected_source": case.get("expected_source"),
            "r0_hit_at_3": case.get("expected_source") in [h["source"] for h in r0_hits] if category == "knowledge" else None,
            "r1_hit_at_3": case.get("expected_source") in [h["source"] for h in r1_hits] if category == "knowledge" else None,
            "r0_evidence_hit_at_3": any(h["source"] == case.get("expected_source") and case["expected_text"] in h["text"] for h in r0_hits) if category == "knowledge" else None,
            "r1_evidence_hit_at_3": any(h["source"] == case.get("expected_source") and case["expected_text"] in h["content"] for h in r1_hits) if category == "knowledge" else None,
            "r0_evidence_top1": bool(r0_hits and r0_hits[0]["source"] == case.get("expected_source") and case["expected_text"] in r0_hits[0]["text"]) if category == "knowledge" else None,
            "r0_heading_evidence_top1": bool(r0_heading_hits and r0_heading_hits[0]["source"] == case.get("expected_source") and case["expected_text"] in r0_heading_hits[0]["text"]) if category == "knowledge" else None,
            "r1_evidence_top1": bool(r1_hits and r1_hits[0]["source"] == case.get("expected_source") and case["expected_text"] in r1_hits[0]["content"]) if category == "knowledge" else None,
            "r0_top3": [{"source": h["source"], "score": h["score"], "start": h["start"], "excerpt": h["text"][:140]} for h in r0_hits],
            "r0_heading_top3": [{"source": h["source"], "score": h["score"], "excerpt": h["text"][:140]} for h in r0_heading_hits],
            "r1_top3": [{"source": h["source"], "heading": h["heading"], "rerank_score": h["rerank_score"], "excerpt": h["content"][:140]} for h in r1_hits],
            "agent_answer": response.answer, "agent_tools": response.tools_used,
            "agent_citations": response.citations, "agent_pending": bool(response.pending_action),
            "agent_checks": checks, "agent_rule_check_pass": all(checks.values()),
            "trace_id": response.trace_id,
        }
        rows.append(row)

    trace.close()
    (HERE / "results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    summary = summarize(rows)
    (HERE / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
