"""Offer 查询 Tool。"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client
from ..permissions import enforce_tool


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_offer_custom_fields() -> dict[str, Any]:
        """获取 Offer 自定义字段的定义（社招 / 校招）。

        对应 Moka 接口：GET /offers/custom_fields（v1）

        说明：实测返回结构为 {"social": [...], "campus": [...]}，分别对应
        社招和校招的字段定义（不是通用的 data 字段）。
        """
        enforce_tool("get_offer_custom_fields")
        client = get_client()
        body = await client.get("/offers/custom_fields")
        if isinstance(body, dict):
            return {
                "social": body.get("social"),
                "campus": body.get("campus"),
            }
        return {"data": body}
