"""将每次 Agent 决策写入 JSONL，便于调试和 Bad Case 分析。"""

from __future__ import annotations

import json
import atexit
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .guardrails import redact_sensitive_data


class TraceLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = None
        atexit.register(self.close)

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def log(self, trace_id: str, event: str, payload: dict[str, Any]) -> None:
        safe_payload = json.loads(redact_sensitive_data(json.dumps(payload, ensure_ascii=False, default=str)))
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            "event": event,
            "payload": safe_payload,
        }
        if self._stream is None or self._stream.closed:
            self._stream = self.path.open("a", encoding="utf-8")
        self._stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._stream.flush()

    def close(self) -> None:
        if self._stream is not None and not self._stream.closed:
            self._stream.close()
