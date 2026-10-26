"""运行项目内 Codex 的官方登录流程，不读取或打印认证文件。"""

import argparse
import subprocess
import sys

from models.codex_llm import find_codex, subscription_env
from models.llm import LLMError


def main() -> int:
    parser = argparse.ArgumentParser(description="登录 Codex 订阅账号")
    parser.add_argument("--status", action="store_true", help="查看登录方式，不发起登录")
    args = parser.parse_args()
    try:
        command = [find_codex(), "login"]
        if args.status:
            command.append("status")
        else:
            print("请在随后打开的浏览器中登录拥有 Codex 权限的 ChatGPT 账号。", flush=True)
        return subprocess.call(command, env=subscription_env())
    except (LLMError, OSError) as exc:
        print(f"登录工具启动失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
