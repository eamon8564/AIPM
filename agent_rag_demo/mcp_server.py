"""本地 MCP Server：通过 stdio 暴露电商知识与订单工具。"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from agent_app.config import get_settings
from agent_app.tools import ToolService


settings = get_settings()
service = ToolService(
    settings.data_dir,
    settings.runtime_dir,
    settings.chunk_size,
    settings.chunk_overlap,
    settings.top_k,
    settings.min_retrieval_score,
)
server = FastMCP("starbridge-commerce-tools")


@server.tool()
def search_knowledge(query: str, top_k: int = 3) -> dict:
    """Search product, shipping, returns and membership knowledge."""
    return service.search_knowledge(query, top_k)


@server.tool()
def query_order(order_id: str) -> dict:
    """Query a mock order."""
    return service.query_order(order_id)


@server.tool()
def track_logistics(order_id: str) -> dict:
    """Track a mock order's logistics."""
    return service.track_logistics(order_id)


@server.tool()
def check_return_eligibility(order_id: str) -> dict:
    """Check return eligibility for a mock order."""
    return service.check_return_eligibility(order_id)


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    server.run(transport=transport)
