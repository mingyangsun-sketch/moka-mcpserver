"""组织架构（部门）查询 Tool。"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client
from ..permissions import authorize


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_departments() -> dict[str, Any]:
        """查询部门列表（树形组织架构）。

        对应 Moka 接口：GET /departments（v1）

        说明：实测返回结构为 {"departments": [...]}（不是通用的 data 字段）。
        """
        await authorize("list_departments")
        client = get_client()
        body = await client.get("/departments")
        data = body.get("departments") if isinstance(body, dict) else body
        return {"departments": data}
