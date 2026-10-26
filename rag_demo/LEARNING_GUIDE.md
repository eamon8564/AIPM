# 从 0 理解 Codex 配置与 RAG 调试

目标：你能解释每一步在做什么，自己选择模型、查看真实输入、定位错误，并进行一次可比较的实验。先跑通一条问题，再研究参数，不需要先学完所有 Codex 配置。

## 0. 先分清三个角色

| 角色 | 在这个项目中的工作 | 你控制什么 |
|---|---|---|
| Python RAG 程序 | 读取 Markdown、切块、TF-IDF 检索、组装问题和证据 | 文档、chunk_size、overlap、K、阈值、Prompt |
| Codex CLI | 登录、启动一次 Agent 调用、接收文本并返回事件 | 模型 ID、推理强度、运行权限 |
| 底层模型 | 根据上下文产生文本 | 通过 Codex 参数选择；不是在 TF-IDF 中选择 |

`--backend codex` 表示 Python 调用本地 Codex 程序。不是连接当前桌面聊天，也不会自动继承这段聊天的历史或你给桌面聊天选择的模型。每道题都是一个新会话。

原版没有写死模型：CLI 命令没有 `--model`，具体由 Codex 默认行为决定。不能据此宣称用了某个固定型号。现在已增加 `--codex-model` 和 `--codex-effort`，便于显式选择和记录实验条件。

## 1. 准备终端并确认账号

打开自己的 PowerShell，运行：

```powershell
Set-Location .\rag_demo
python --version
python codex_login.py --status
```

`&` 是 PowerShell 的调用运算符，表示执行后面的程序路径。`app.py`、`codex_login.py` 是传给 Python 的脚本；以 `--` 开头的是脚本参数。参数一般只影响这一次运行，不会改写代码。

如果不是 `Logged in using ChatGPT`，先运行：

```powershell
python codex_login.py
```

在浏览器中完成订阅账号登录后再检查状态。检查状态不发起模型问答。不要填写 LLM_API_KEY；它用于另一条 API 接入路径。

## 2. 先证明检索独立可用

```powershell
python app.py --retrieval-only -q '购买商品后多少天内可以申请退货？'
```

预期看到 `returns.md#1` 等片段，以及“未执行 LLM 生成”。找到原文中的“签收次日起 7 个自然日”，再看商品完好与例外条件。能检索到文档不代表全部答案证据都已经出现在片段里。

查看切块：

```powershell
python app.py --show-chunks
```

观察相邻块重复了哪些字，是否把同一规则的条件切开。默认 size=300、overlap=60，所以窗口步长为 240 字符。

## 3. 找到你账号可用的模型

项目内已有 CLI，但没有设置全局 PATH。以下命令取得其位置并打开交互界面：

```powershell
$codexExe = python -c 'from models.codex_llm import find_codex; print(find_codex())'
& $codexExe --version
& $codexExe
```

进入 Codex 界面后，依次输入：

```text
/model
/status
```

在 `/model` 中查看账号可选模型和支持的推理强度。选定后，用 `/status` 查看当前会话信息，记下模型 ID。可用列表取决于账号、客户端和组织设置，不能直接把网上某个旧型号当成你可用的模型。完成后用 Ctrl+C 退出，回到 PowerShell。

注意：这里是独立的交互式 Codex 会话，它可能读取你的个人配置；Demo 的生成调用不会读取个人 config.toml。需要把你选的模型 ID 显式传给 Demo。

## 4. 在 Demo 中显式选择模型

用输入提示把刚才看到的模型 ID 保存到一个 PowerShell 变量：

```powershell
$modelId = Read-Host '输入刚才确认可用的模型 ID'
```

先查看请求配置，不调用模型：

```powershell
python app.py --backend codex --codex-model $modelId --show-config
```

再实际运行：

```powershell
python app.py --backend codex --codex-model $modelId -q '购买商品后多少天内可以申请退货？'
```

终端会显示请求的模型、推理强度、检索参数、状态、耗时、回答和引用。“请求的模型”是程序传入的参数，不是对服务端内部执行型号的独立鉴定。不要通过问模型“你是什么模型”来验证配置。

如果你选的模型支持 `medium`，可显式加上：

```powershell
python app.py --backend codex --codex-model $modelId --codex-effort medium -q '购买商品后多少天内可以申请退货？'
```

推理强度表示给模型的推理投入设置，不是温度，也不是答案可信度。更高强度不保证简单客服题更正确。先用模型默认强度，再测试该模型支持的其他级别。本 Demo 接收 low、medium、high、xhigh、max、ultra，但服务端不一定接受每个模型的所有级别；入门先研究默认、low、medium 即可。

## 5. 理解配置在哪里生效

| 设置入口 | 影响本 Demo 的 Codex 生成吗？ |
|---|---|
| 桌面聊天里选择的模型 | 不自动传给这个 Python 程序 |
| 用户目录下的 `.codex/config.toml` | 当前适配器使用 `--ignore-user-config`，不加载这个文件 |
| `LLM_MODEL` 环境变量 | 只给 `--backend api` 使用 |
| `--codex-model` | 是，转成 Codex CLI 的 `--model` |
| `--codex-effort` | 是，转成 `-c model_reasoning_effort="..."` |
| 组织管理策略 | 仍可能约束模型可用性与权限 |

普通 Codex 客户端可以在用户 config.toml 中写类似配置：

```toml
# 示例占位符，必须换成账号实际可用的 ID
model = "你的模型ID"
model_reasoning_effort = "medium"
```

默认位置通常是 `%USERPROFILE%\.codex\config.toml`；设置了 CODEX_HOME 时位置会改变。这个知识有助于理解 Codex，但本 Demo 的参数实验无需修改全局文件。这里保留忽略个人配置，是为了减少个人插件、模型偏好等对实验的干扰。

其他运行参数：`read-only` 限制文件写入，不等于阻止读取所有文件；`--ephemeral` 不保留常规会话记录，不等于向服务商发送请求后完全没有任何记录；空临时目录避免直接把项目目录作为工作上下文；`--skip-git-repo-check` 允许在该临时目录启动。

## 6. 看清模型真正收到了什么

先只预览，不调用 Codex：

```powershell
python app.py --backend codex --retrieval-only --show-prompt -q '购买商品后多少天内可以申请退货？'
```

你会看到两层内容：

1. `pipeline.py` 组装的 messages：回答规则 + 用户问题 + 带编号的知识片段。
2. `codex_llm.py` 转换后的 CLI 文本：包含“只使用这些片段、不使用工具”的约束，以及展开的 messages。

这就是程序经标准输入发给 CLI 的文本，不包括 Codex 自己的内部系统指令。这里的 `system:` 是文本标签，并没有像直接调用 Chat Completions API 那样建立独立的系统角色。Codex 内部规则仍然存在，这是两条接入路径的重要区别。

通过 `--show-prompt` 查看输入，才能判断答案错误是因为模型没有证据，还是它拿到证据后仍然答错。它不会显示模型完整的内部思考过程，调试也不需要依赖那种内容。

## 7. 按层定位错误

| 现象 | 先检查 | 建议动作 |
|---|---|---|
| `python` 或 `codex` 找不到 | 程序位置 | 使用本文的绝对 Python 路径和项目内 CLI |
| 未确认订阅登录 | `codex_login.py --status` | 在自己的 PowerShell 中完成官方登录 |
| 缺少 LLM_API_KEY | 是否忘记 backend | 加 `--backend codex` |
| `no_evidence` | 召回分数和文本 | 先检查文档是否包含答案，再研究阈值 |
| 召回错误文档 | 查询措辞与 TF-IDF | 看是否缺少词面重合；尝试同义改写作为失败样本 |
| 文件命中但缺少条件 | Chunk 和 Top-K | 看被截断的规则与例外是否在另一块 |
| 证据正确、回答错误 | 实际 Prompt 和引用 | 固定检索，调整 Prompt 或模型并对照 |
| Codex 调用失败 | 登录、模型 ID、强度、网络、额度 | 用下面的 CLI 单独验证；原始诊断留在自己终端查看 |
| 工具使用被拒绝展示 | Codex 事件 | 说明调用偏离了纯文本实验；不计作 RAG 成功回答 |

单独验证 Codex，暂时不经过 Python RAG（会使用订阅额度）：

```powershell
& $codexExe exec --ignore-user-config --ephemeral --sandbox read-only --skip-git-repo-check --model $modelId '不要调用工具，只回复：连接成功'
```

直接运行时可以看到 CLI 原始诊断，包括模型不可用、认证或网络问题。这个命令验证“CLI 能否调用模型”，不验证 RAG 答案质量。如果此处失败，先解决 CLI；如果此处成功而 Demo 失败，再看适配器的事件检查和 Prompt。完整错误信息可能包含本地路径等信息，分享时只截取相关错误，不提供认证文件。

## 8. 从代码理解一次调用

按顺序查看：

1. `app.py`：`argparse` 将 `--codex-model` 等参数变成 `args`；`show_answer()` 传入流程并显示结果。
2. `rag/pipeline.py`：`__init__()` 读取文档、切块并建索引；`ask()` 调用检索，再判断能否生成。
3. `rag/retriever.py`：`search()` 转换问题向量，算 cosine similarity，排序取 K。
4. `rag/pipeline.py`：`build_messages()` 添加规则、问题和证据编号。
5. `models/codex_llm.py`：`build_codex_prompt()` 转成文本；`build_codex_command()` 添加模型与推理参数；`generate_codex()` 调用 CLI 并解析事件。
6. 回到 `rag/pipeline.py`：提取答案中的 `[1]` 等引用；返回 `RAGResponse`。
7. 回到 `app.py`：打印回答与来源。

`subprocess.run()` 相当于“Python 帮你启动另一个程序”。`input=prompt` 是标准输入，`stdout` 是标准输出，`stderr` 是诊断信息。`--json` 返回的是一行一个 JSON 的事件流，不能把它整体当成一个 JSON 对象。适配器从 `item.completed` 中取回答，并要求出现 `turn.completed` 才认为调用完整。

### 亲手暂停程序看变量

先只调试检索。在 `rag/pipeline.py` 中找到：

```python
results = self.retriever.search(question, top_k)
```

临时在它下面添加一行：

```python
breakpoint()
```

运行：

```powershell
python app.py --retrieval-only -q '购买商品后多少天内可以申请退货？'
```

看到 `(Pdb)` 后输入以下命令，每次一行：

```text
p question
p top_k
p len(results)
p results[0].score
p results[0].chunk.source
p results[0].chunk.text
n
p messages
c
```

`p` 查看变量，`n` 执行下一行，`c` 继续，`q` 退出调试。此例 `n` 执行 `messages = build_messages(...)` 后就能查看 messages。完成后删除 `breakpoint()`，避免下次普通运行意外暂停。若查询没有结果，不要访问 `results[0]`。

## 9. 完成一次 AI PM 小实验

先固定同一个模型、推理强度和问题，只改变 Top-K。以下命令中的 `$modelId` 需已按第 4 步设置：

```powershell
python app.py --backend codex --codex-model $modelId --top-k 1 -q '退货验收通过后多久退款到账？'
python app.py --backend codex --codex-model $modelId --top-k 3 -q '退货验收通过后多久退款到账？'
```

记录：

| 实验 | 模型/强度 | Size/Overlap/K | 证据是否完整 | 回答是否正确 | 引用是否支持 | 耗时 |
|---|---|---|---|---|---|---|
| A | 记录实际请求设置 | 300/60/1 | | | | |
| B | 与 A 相同 | 300/60/3 | | | | |

该题必须区分“验收后 2 个工作日内发起”和“发起后预计 1～3 个工作日到账”。两次答案相同也有价值：说明这道题可能并不依赖更多召回片段。不要为追求差异而只挑有利结果。

之后分别做：只改 chunk_size；只改推理强度；只换模型；加入 Q8 无答案题。单次回答有随机性，重要比较重复几次。程序显示的时间是检索 + 登录检查 + CLI 启动 + 生成的总耗时，不含启动建索引，不能直接称为纯模型延迟。

测试命令：

```powershell
python -m unittest discover -s tests -v
```

离线测试验证程序行为，不调用真实 Codex。真正的回答正确率、拒答能力与耗时需要在你的登录环境中测量。

## 官方资料

- [模型选择](https://learn.chatgpt.com/docs/models)：交互模式 `/model` 和 CLI `--model`。
- [配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)：模型与推理强度设置。
- [非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)：stdin、JSONL 与忽略个人配置。
- [认证](https://learn.chatgpt.com/docs/auth)：订阅账号登录与状态检查。
