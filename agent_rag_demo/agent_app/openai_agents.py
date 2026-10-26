"""OpenAI Agents SDK 集成：多 Agent、工具调用、Tracing 与人工审批。"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from agents import Agent, Runner, function_tool

from .config import Settings
from .tools import ToolService


_SERVICE: ToolService | None = None


def configure_service(service: ToolService) -> None:
    global _SERVICE
    _SERVICE = service


def _service() -> ToolService:
    if _SERVICE is None:
        raise RuntimeError("ToolService 尚未初始化")
    return _SERVICE


@function_tool
def search_knowledge(query: str, top_k: int = 3) -> str:
    """Search the store knowledge base and return evidence with source files and scores."""
    return json.dumps(_service().search_knowledge(query, top_k), ensure_ascii=False)


@function_tool
def query_order(order_id: str) -> str:
    """Look up a mock order by order ID such as ORD1001."""
    return json.dumps(_service().query_order(order_id), ensure_ascii=False)


@function_tool
def track_logistics(order_id: str) -> str:
    """Get the carrier, latest logistics event and estimated delivery for a mock order."""
    return json.dumps(_service().track_logistics(order_id), ensure_ascii=False)


@function_tool
def check_return_eligibility(order_id: str) -> str:
    """Check whether a mock order meets the store's return-window rules."""
    return json.dumps(_service().check_return_eligibility(order_id), ensure_ascii=False)


@function_tool(needs_approval=True)
def create_after_sales_ticket(order_id: str, reason: str) -> str:
    """Create an after-sales ticket. This side effect always requires human approval."""
    return json.dumps(_service().create_after_sales_ticket(order_id, reason), ensure_ascii=False)


class AgentSDKRunner:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.history: list[dict] = []

    async def run_turn(
        self,
        question: str,
        approval_callback: Callable[[str], bool],
    ) -> str:
        run_input = [*self.history, {"role": "user", "content": question}]
        result = await Runner.run(self.agent, run_input)
        while result.interruptions:
            state = result.to_state()
            for interruption in result.interruptions:
                approved = approval_callback(str(interruption))
                if approved:
                    state.approve(interruption)
                else:
                    state.reject(interruption)
            result = await Runner.run(self.agent, state)
        self.history = result.to_input_list()
        return str(result.final_output or "未生成最终回答。")


def _agent_kwargs(settings: Settings) -> dict:
    return {"model": settings.openai_model} if settings.openai_model else {}


def build_multi_agent_runner(service: ToolService, settings: Settings) -> AgentSDKRunner:
    """Manager-style 多 Agent：主 Agent 保持最终回答所有权。"""
    configure_service(service)
    model_kwargs = _agent_kwargs(settings)

    knowledge_agent = Agent(
        name="Knowledge Specialist",
        instructions=(
            "只处理商品、配送、退换货政策和会员规则。必须先调用 search_knowledge，"
            "仅依据返回证据回答，证据不足时明确说明无法确认，并保留来源文件。"
        ),
        tools=[search_knowledge],
        **model_kwargs,
    )
    order_agent = Agent(
        name="Order and Logistics Specialist",
        instructions=(
            "处理模拟订单和物流查询。缺少订单号时先要求补充；"
            "不得编造订单状态、承运商或预计时间。"
        ),
        tools=[query_order, track_logistics],
        **model_kwargs,
    )
    after_sales_agent = Agent(
        name="After-sales Specialist",
        instructions=(
            "处理退货资格和售后工单。先调用 check_return_eligibility。"
            "只有用户明确要求创建工单且资格允许时，才调用 create_after_sales_ticket；"
            "该工具会暂停并等待人工审批。"
        ),
        tools=[check_return_eligibility, create_after_sales_ticket, search_knowledge],
        **model_kwargs,
    )

    manager = Agent(
        name="E-commerce Service Manager",
        instructions=(
            "你是星桥优选智能客服调度 Agent。根据问题选择合适的专业 Agent 工具，"
            "可以组合多个工具，但不要重复调用。最终使用中文简洁回答，说明信息来源；"
            "工具没有证据时必须拒答，不得猜测。高风险操作必须等待人工审批。"
        ),
        tools=[
            knowledge_agent.as_tool(
                tool_name="ask_knowledge_specialist",
                tool_description="查询商品、配送、退换货政策和会员知识。",
            ),
            order_agent.as_tool(
                tool_name="ask_order_specialist",
                tool_description="查询模拟订单状态和实时物流数据。",
            ),
            after_sales_agent.as_tool(
                tool_name="ask_after_sales_specialist",
                tool_description="判断退货资格或创建需要审批的售后工单。",
            ),
        ],
        **model_kwargs,
    )
    return AgentSDKRunner(manager)


@asynccontextmanager
async def build_mcp_runner(
    service: ToolService,
    settings: Settings,
    server_script: Path,
):
    """通过 stdio 启动本地 MCP Server，并将业务工具挂到 Agent。"""
    from agents.mcp import MCPServerStdio

    configure_service(service)
    server_context = MCPServerStdio(
        name="starbridge-commerce-tools",
        params={
            "command": sys.executable,
            "args": [str(server_script), "stdio"],
            "cwd": str(settings.project_root),
            "env": dict(os.environ),
        },
        cache_tools_list=True,
    )
    async with server_context as server:
        agent = Agent(
            name="MCP E-commerce Service Agent",
            instructions=(
                "使用 MCP 工具完成知识检索、订单、物流和退货资格查询。"
                "创建售后工单时使用需要人工审批的 create_after_sales_ticket。"
                "仅依据工具结果回答，证据不足时明确拒答。"
            ),
            tools=[create_after_sales_ticket],
            mcp_servers=[server],
            **_agent_kwargs(settings),
        )
        yield AgentSDKRunner(agent)
