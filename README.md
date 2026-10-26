# AIPM 作品集

本仓库收录一个电商客服 RAG 教学 Demo，以及基于公开资料撰写的产品反向 PRD 分析。

## 内容

| 目录 | 内容 |
| --- | --- |
| [rag_demo](rag_demo/README.md) | 虚构电商“星桥优选”的命令行 RAG 客服，包含知识库、检索与生成流程、测试和学习指南。 |
| [reverse-prd/ChatGPT反向PRD.md](reverse-prd/ChatGPT反向PRD.md) | ChatGPT 助手产品的反向 PRD。 |
| [reverse-prd/豆包反向PRD.md](reverse-prd/豆包反向PRD.md) | 豆包 AI 助手产品的反向 PRD。 |

反向 PRD 是个人学习分析，文中区分公开事实、推断与设计建议；不代表相关公司的内部文档。

## 运行 RAG Demo

需要 Python 3.10 或更高版本。在仓库根目录执行：

```powershell
Set-Location rag_demo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --retrieval-only -q '购买商品后多少天内可以申请退货？'
```

仅检索模式无需 API Key。生成回答的配置、Codex 可选模式与限制见 [RAG Demo 说明](rag_demo/README.md)。

运行测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
