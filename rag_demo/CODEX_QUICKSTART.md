# 使用你的 Codex 订阅运行 RAG Demo

想理解模型配置、Prompt 和断点调试，请按 [从 0 学习指南](LEARNING_GUIDE.md) 操作。现在支持 `--codex-model`、`--codex-effort` 和 `--show-config`。

项目提供 Codex CLI 的 npm 依赖配置，并增加 `--backend codex`。首次使用先运行 `npm.cmd ci --prefix tools/codex` 安装。这里直接调用 CLI，不需要安装 Python SDK，也不需要填写 LLM_API_KEY。默认 API 模式保持原样。

## 1. 打开 PowerShell，进入项目

```powershell
Set-Location .\rag_demo
```

## 2. 登录订阅账号（首次使用）

```powershell
python codex_login.py
```

按照提示在浏览器中登录你购买订阅、具有 Codex 访问权限的 ChatGPT 账号。不要选择 API Key 登录。浏览器登录完成后返回终端。

检查状态：

```powershell
python codex_login.py --status
```

输出应表明使用 ChatGPT 登录，例如 `Logged in using ChatGPT`。如果已经登录相同账号，可直接检查状态并跳过重新登录。登录由官方 CLI 处理，不要把密码或认证文件发到聊天里。

## 3. 运行一次问答

```powershell
python app.py --backend codex -q '购买商品后多少天内可以申请退货？'
```

成功时会展示检索片段、相似度分数、`generated` 状态、Codex 回答和引用。答案应依据召回内容说明签收次日起 7 个自然日及适用条件。调用可能需要几十秒，程序设置了 180 秒超时。

连续输入问题：

```powershell
python app.py --backend codex
```

输入 `退出` 结束。每道题独立运行，不共享对话记忆。

## 4. 对照实验

```powershell
# 只看检索，不调用 Codex
python app.py --backend codex --retrieval-only -q '购买商品后多少天内可以申请退货？'

# 信息不足题：观察模型是否说明无法确认
python app.py --backend codex -q '金卡会员购买晨光保温杯可以免费刻字吗？'
```

## 安装位置与运行方式

CLI 安装在本项目 `tools/codex/node_modules`，没有要求全局安装，也不需要把 codex 添加到 PATH。如果复制项目到新电脑，先安装 Node.js/npm，再在本项目目录恢复安装：

```powershell
npm.cmd ci --prefix tools/codex
```

Python 依赖仍为 `requirements.txt` 中的 scikit-learn。代码使用 Python 标准库 subprocess 调用原生 Codex 程序，将 Prompt 通过标准输入传入，解析 JSONL 返回结果。`models/codex_llm.py` 是新增生成适配器；`codex_login.py` 只负责启动官方登录/状态命令。

程序先确认 ChatGPT 登录，并从子进程环境移除 OPENAI_API_KEY、CODEX_API_KEY；不会自动回退到付费 API。请求使用空临时工作目录、只读沙箱和 `--ignore-user-config`，因此不使用个人 config.toml 中的模型或 MCP 配置。使用 `--codex-model` 显式选择模型；未指定时交由 Codex 决定，不声称已经核实具体型号。组织策略仍可能影响权限和可用模型。

Prompt 要求不执行工具。若返回事件显示使用了额外工具，程序会拒绝将其输出展示成纯 RAG 答案；这属于事后检查，并不是绝对禁止工具执行。只读沙箱也不是完全禁止文件读取。这个模式用于个人本地学习，不代表生产级隔离。

## 常见情况

- **缺少 LLM_API_KEY**：很可能没有传 `--backend codex`；默认仍是原来的 API 模式。
- **未确认 ChatGPT 订阅登录**：运行上述登录命令，随后用 `--status` 检查。
- **Could not find home directory**：请在你自己的 Windows PowerShell 中运行，不要在缺少用户主目录的服务/受限终端中启动。
- **调用失败/超时**：检查登录状态、网络、账号模型权限和订阅额度。失败时仍会展示本地检索结果，不会冒充已生成答案。
- **额外工具提示**：本次 Codex 输出不符合仅依据传入片段的实验要求，不能计入纯 RAG 答案质量评测。

本次共 20 项离线测试通过，其中 7 项覆盖 Codex 模型/强度参数、认证判断、无 Key 路由、请求/响应、工具事件拒绝和超时等情况。测试使用模拟 Codex 响应；真实订阅登录和生成需要在你的终端完成。订阅使用受账号权限和额度约束，并非无限调用。

官方参考：[认证说明](https://learn.chatgpt.com/docs/auth)、[非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)。
