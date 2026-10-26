"""使用标准库请求兼容 Chat Completions 的 API，无需额外 SDK。"""

import json
import os
from dataclasses import dataclass, field
from urllib import error, request
from urllib.parse import urlparse


class LLMError(RuntimeError):
    """接口错误可恢复：CLI 应继续展示检索结果。"""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = field(repr=False)
    base_url: str = ""
    model: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(*(os.getenv(name, "").strip() for name in (
            "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"
        )))

    def missing(self) -> list[str]:
        return [name for name, value in (
            ("LLM_API_KEY", self.api_key),
            ("LLM_BASE_URL", self.base_url),
            ("LLM_MODEL", self.model),
        ) if not value]


def generate(messages: list[dict[str, str]], config: LLMConfig) -> str:
    """发送非流式请求，返回回答文本；错误信息不回显 Key 或响应原文。"""
    if config.missing():
        raise LLMError("LLM 配置不完整。")
    parsed = urlparse(config.base_url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise LLMError("LLM_BASE_URL 必须是有效的 HTTP(S) API 根地址。")
    payload = json.dumps({
        "model": config.model, "messages": messages, "stream": False
    }, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        config.base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {config.api_key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            result = json.load(response)
        answer = result["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise LLMError("API 未返回有效回答文本。")
        return answer.strip()
    except error.HTTPError as exc:
        raise LLMError(f"LLM API 返回 HTTP {exc.code}，请检查权限、模型和额度。") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise LLMError("LLM API 连接失败或超时，请检查网络与地址。") from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("API 响应不符合 Chat Completions 格式。") from exc
