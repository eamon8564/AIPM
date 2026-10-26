"""通过官方 CLI 使用 Codex 订阅登录；无需 Python SDK 或 API Key。"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from models.llm import LLMError


ROOT = Path(__file__).resolve().parents[1]


def find_codex() -> str:
    """优先使用项目内安装的 Windows 原生程序，避免 shell 转义问题。"""
    local = ROOT / "tools" / "codex" / "node_modules" / "@openai"
    candidates = sorted(local.glob("codex-*/vendor/**/codex.exe"))
    if candidates:
        return str(candidates[0])
    executable = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if executable:
        return executable
    raise LLMError("未找到 Codex CLI。请在项目目录执行 npm.cmd ci --prefix tools/codex。")


def subscription_env() -> dict[str, str]:
    """使用本机已保存的登录；排除通过环境变量切换成 API Key 的情况。"""
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(name, None)
    return env


def build_codex_prompt(messages: list[dict[str, str]]) -> str:
    """CLI 接收一个文本 Prompt；role 标签在这里是文本，不是 API 的角色字段。"""
    return (
        "这是纯文本 RAG 问答。仅使用下面给出的片段，不调用任何工具、"
        "不读取文件、不搜索网页。只输出最终中文回答，保留 [1] 形式的引用。\n\n"
        + "\n\n".join(f"{m['role']}:\n{m['content']}" for m in messages)
    )


def build_codex_command(executable: str, folder: str, model: str | None = None,
                        effort: str | None = None) -> list[str]:
    """显式传递实验参数；不设置时交由 CLI 决定，不声称已知实际模型。"""
    command = [executable, "exec", "--ignore-user-config", "--ephemeral",
               "--skip-git-repo-check", "--sandbox", "read-only", "--json",
               "--color", "never", "-C", folder]
    if model:
        command.extend(["--model", model])
    if effort:
        command.extend(["-c", f"model_reasoning_effort={json.dumps(effort)}"])
    return command + ["-"]


def generate_codex(messages: list[dict[str, str]], model: str | None = None,
                   effort: str | None = None) -> str:
    """把 RAG Prompt 经 stdin 送给 Codex，读取 JSONL 中的最终回答。"""
    executable = find_codex()
    env = subscription_env()
    try:
        status = subprocess.run(
            [executable, "login", "status"], capture_output=True,
            encoding="utf-8", errors="replace", env=env, timeout=20,
        )
        if status.returncode or "chatgpt" not in (status.stdout + status.stderr).lower():
            raise LLMError("未确认 ChatGPT 订阅登录。请先运行 python codex_login.py，"
                           "在浏览器登录订阅账号，再运行 python codex_login.py --status。")
        prompt = build_codex_prompt(messages)
        # 空工作目录避免主动带入项目资料；read-only 不等于禁止读取一切文件。
        # 不加载用户工具配置；此外检查事件，拒绝将工具执行后的输出当作纯 RAG 回答。
        with TemporaryDirectory(prefix="rag-codex-") as folder:
            completed = subprocess.run(
                build_codex_command(executable, folder, model, effort),
                input=prompt, capture_output=True, encoding="utf-8", errors="replace",
                env=env, timeout=180,
            )
        if completed.returncode:
            raise LLMError("Codex 调用失败，请检查订阅额度、网络及登录状态。"
                           "可运行 python codex_login.py --status 查看认证状态。")
        answer = ""
        finished = False
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") in ("error", "turn.failed"):
                raise LLMError("Codex 未完成回答，请检查网络、账号权限或订阅额度。")
            item = event.get("item")
            if item:
                if item.get("type") not in ("agent_message", "reasoning", "plan"):
                    raise LLMError("Codex 使用了额外工具，本次输出不作为纯 RAG 回答展示。")
                if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                    answer = item.get("text", "")
            if event.get("type") == "turn.completed":
                finished = True
        if not finished or not isinstance(answer, str) or not answer.strip():
            raise LLMError("Codex 没有返回完整的文本回答。")
        return answer.strip()
    except subprocess.TimeoutExpired as exc:
        raise LLMError("Codex 登录检查或生成超时；检索结果仍可查看。") from exc
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise LLMError("无法运行 Codex 或解析其输出，请检查安装和运行环境。") from exc
