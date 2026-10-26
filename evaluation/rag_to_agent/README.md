# 电商客服 RAG 到 Agent 的离线评测

此目录记录虚构电商客服教学原型从静态 RAG 问答扩展到工具型 Agent 的评测。所有新增知识规则、订单和问题均为**模拟数据**，数字不代表真实电商业务效果。原 RAG 代码位于 [`../../rag_demo`](../../rag_demo/README.md)，Agent 原型位于 [`../../agent_rag_demo`](../../agent_rag_demo/README.md)。

## 结果概览

| 指标 | 原 RAG 检索复现 | 标题切块 TF-IDF | Agent 所用混合检索或本地模式 |
|---|---:|---:|---:|
| 40 条知识题的证据 Top 1 | 34/40 | 37/40 | 37/40 |
| 40 条知识题的证据 Top 3 | 40/40 | 40/40 | 40/40 |
| 知识回答规则检查 | 未运行生成 | 未运行生成 | 34/40 |
| 订单、物流、多轮、售后规则检查 | 功能不存在 | 功能不存在 | 60/60 |
| 边界规则检查 | 不适用 | 不适用 | 11/20 |

标题切块 TF-IDF 与混合检索的 Top 1 总量相同，不能把 3/40 的改善单独归因于 BM25 或重排。5 条跨用户订单查询均未拦截；当前原型没有身份鉴权，不能连接真实订单系统。详见 [逐项评测报告](EVALUATION.md)。

## 文件

- `prepare_fixtures.py`：在本目录重建 8 份知识文档、24 条模拟订单及 120 条案例。
- `run_eval.py`：运行 RAG 检索数学复现、标题切块对照、混合检索及本地确定性 Agent 检查。
- `cases.json`：每题输入、预期、类别及模拟数据标记。
- `fixture_manifest.json`：数据规模与案例拆分。
- `metrics.json`：各组原始计数。
- `results.jsonl`：逐题检索、回答、规则结果及 Trace ID。
- `data/`：复制的原始知识库、扩展的虚构知识、订单快照。

## 复现

在仓库根目录运行，Python 3.10 或更新版本即可；脚本不调用外部 API。

```powershell
python evaluation/rag_to_agent/prepare_fixtures.py
python evaluation/rag_to_agent/run_eval.py
```

`run_eval.py` 会在本目录创建 `runtime/` 轨迹。它使用标准 Python 复现原 RAG 字符 2–4 gram TF-IDF 公式；未调用原 `RAGPipeline` 的 LLM 生成，也未验证 Agent 的 SDK/MCP 在线模式。`dev` 与 `holdout` 由同一模板生成且已检查全部输出，不是独立盲测。
