"""输入与输出的基础安全控制。"""

from __future__ import annotations

import re


MAX_INPUT_LENGTH = 800
SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{15,18}[0-9Xx]\b"),
    re.compile(r"\b1[3-9]\d{9}\b"),
]


def validate_user_input(text: str) -> tuple[bool, str]:
    cleaned = text.strip()
    if not cleaned:
        return False, "问题不能为空。"
    if len(cleaned) > MAX_INPUT_LENGTH:
        return False, f"问题过长，请控制在 {MAX_INPUT_LENGTH} 个字符以内。"
    return True, cleaned


def redact_sensitive_data(text: str) -> str:
    """日志中隐藏可能的身份证号和手机号，不改变实际工具参数。"""
    result = text
    for pattern in SENSITIVE_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def grounded_fallback() -> str:
    return "根据当前知识库和工具返回结果，我暂时无法确认。建议补充订单号或联系人工客服。"
