"""分页工具：基于 Moka 的 `next` 游标自动翻页。"""

from __future__ import annotations

from typing import Any

from ..client import MokaClient


async def fetch_all(
    client: MokaClient,
    path: str,
    *,
    version: str = "v1",
    params: dict[str, Any] | None = None,
    data_key: str = "data",
    next_key: str = "next",
    max_items: int | None = None,
    stage_query: bool = False,
) -> list[Any]:
    """沿 `next` 游标自动翻页，返回汇总后的数据列表。

    - version：v1 / v2 / candidate/v1。
    - data_key：响应体中数据列表所在的字段名（Moka 多为 "data"）。
    - next_key：响应体中下一页游标所在的字段名（Moka 多为 "next"）。
    - max_items：最多返回多少条，None 时使用配置里的 max_items 上限。
    """
    limit = max_items if max_items is not None else client.settings.max_items
    collected: list[Any] = []
    cursor: Any = None
    base_params = dict(params or {})

    while True:
        page_params = dict(base_params)
        if cursor:
            page_params["next"] = cursor

        body = await client.get(
            path, version=version, params=page_params, stage_query=stage_query
        )

        # 兼容：响应可能直接是 list，也可能是 {data: [...], next: ...}
        if isinstance(body, list):
            rows = body
            cursor = None
        elif isinstance(body, dict):
            rows = body.get(data_key) or []
            cursor = body.get(next_key)
        else:
            rows = []
            cursor = None

        if not isinstance(rows, list):
            rows = [rows]

        collected.extend(rows)

        if len(collected) >= limit:
            return collected[:limit]
        if not cursor:
            return collected
