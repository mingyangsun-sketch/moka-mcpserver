"""人才库（Talent Pool）查询 Tool。

生产环境实测校准：
- 列表：GET v1 /talentPool/list，直接返回数组。
- 候选人：GET v1 /talentPool/candidates，必填 archivedAtStart/archivedAtEnd/talentPoolIds。
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client
from ..utils.sanitize import sanitize


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_talent_pools() -> dict[str, Any]:
        """查询所有人才库。

        对应 Moka 接口：GET /talentPool/list（v1）

        返回每个人才库的 id、name、hireMode、isPrivate 等（实测直接返回数组）。
        """
        client = get_client()
        body = await client.get("/talentPool/list")
        pools = body if isinstance(body, list) else body.get("data")
        return {"talent_pools": pools}

    @mcp.tool()
    async def list_talent_pool_candidates(
        talent_pool_ids: list[int],
        archived_at_start: str,
        archived_at_end: str,
    ) -> dict[str, Any]:
        """查询指定人才库下的候选人（按归档时间范围）。

        对应 Moka 接口：GET /talentPool/candidates（v1）

        参数（均必填）：
        - talent_pool_ids：人才库 ID 列表，如 [666, 888]。
        - archived_at_start：归档开始时间，如 "2019-06-01"。
        - archived_at_end：归档结束时间，如 "2019-11-01"。
        """
        client = get_client()
        ids_param = "[" + ",".join(str(i) for i in talent_pool_ids) + "]"
        body = await client.get(
            "/talentPool/candidates",
            params={
                "talentPoolIds": ids_param,
                "archivedAtStart": archived_at_start,
                "archivedAtEnd": archived_at_end,
            },
        )
        data = body.get("data") if isinstance(body, dict) else None
        candidates = data.get("candidates") if isinstance(data, dict) else data
        masked = sanitize(candidates, enabled=client.settings.mask_sensitive)
        return {
            "total": len(masked) if isinstance(masked, list) else 0,
            "candidates": masked,
        }
