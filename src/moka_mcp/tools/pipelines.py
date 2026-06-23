"""招聘流程（Pipeline / Stage）查询 Tool。

注意：这两个接口实测在 **v2** 路径下。
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_pipelines() -> dict[str, Any]:
        """获取招聘流程（Pipeline）列表。

        对应 Moka 接口：GET /pipelines/getPipelinesList（v2）

        返回每个流程的 id、name、hireMode、entryConditions 等。
        """
        client = get_client()
        body = await client.get("/pipelines/getPipelinesList", version="v2")
        data = body.get("data") if isinstance(body, dict) else body
        return {"pipelines": data}

    @mcp.tool()
    async def list_stages(pipeline_id: str | None = None) -> dict[str, Any]:
        """获取招聘阶段（Stage）信息列表。

        对应 Moka 接口：GET /stage/getStagesList（v2）

        参数：
        - pipeline_id：可选，按指定流程过滤阶段。

        返回每个阶段的 id、name、type。
        """
        client = get_client()
        params = {"pipelineId": pipeline_id} if pipeline_id else None
        body = await client.get("/stage/getStagesList", version="v2", params=params)
        data = body.get("data") if isinstance(body, dict) else body
        return {"stages": data}
