"""职位查询相关 Tool。

生产环境实测校准：
- 列表：GET v1 /jobs/{orgId}，mode（social/campus）必填，返回 {jobs, total}。
- 详情：GET v1 /jobs/{orgId}/{jobId}，返回扁平对象（含 customFields/pipelineId/pipelineName）。
- 职位自定义字段没有稳定的独立读取接口，故从职位详情的 customFields 提取。
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import get_client
from ..permissions import enforce_tool, filter_jobs

Mode = Literal["social", "campus"]


def _resolve_org_id(explicit: str | None) -> str:
    client = get_client()
    org_id = explicit or client.settings.org_id
    if not org_id:
        raise ValueError(
            "缺少 orgId：请在调用时传入 org_id，或在 .env 中配置 MOKA_ORG_ID。"
        )
    return org_id


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_jobs(
        mode: Mode,
        org_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """查询职位列表。

        对应 Moka 接口：GET /jobs/{orgId}（v1）

        参数：
        - mode：招聘模式，**必填**。social=社招 / campus=校招。
        - org_id：组织标识；留空则使用 .env 中的 MOKA_ORG_ID。
        - limit：返回条数上限。

        说明：已关闭但未勾选「取消在官网显示」的职位仍会返回；已删除职位不返回。
        """
        enforce_tool("list_jobs")
        client = get_client()
        oid = _resolve_org_id(org_id)
        body = await client.get(
            f"/jobs/{oid}", params={"mode": mode, "limit": limit}
        )
        jobs = body.get("jobs", []) if isinstance(body, dict) else body
        jobs = filter_jobs(jobs)  # department 范围过滤
        return {"total": len(jobs), "jobs": jobs}

    @mcp.tool()
    async def get_job_detail(
        job_id: str,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        """获取单个职位详情（含自定义字段、招聘流程信息）。

        对应 Moka 接口：GET /jobs/{orgId}/{jobId}（v1）

        参数：
        - job_id：职位 ID。
        - org_id：组织标识；留空则使用 .env 中的 MOKA_ORG_ID。
        """
        enforce_tool("get_job_detail")
        client = get_client()
        oid = _resolve_org_id(org_id)
        body = await client.get(f"/jobs/{oid}/{job_id}")
        # 返回是扁平对象，去掉协议噪声字段
        if isinstance(body, dict):
            job = {k: v for k, v in body.items() if k not in {"code", "msg", "success"}}
        else:
            job = body
        return {"job": job}

    @mcp.tool()
    async def get_job_custom_fields(
        job_id: str,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        """获取某职位的自定义字段。

        实现说明：Moka 没有稳定的独立「职位自定义字段定义」读取接口，
        但职位详情里自带 customFields，故本工具从 GET /jobs/{orgId}/{jobId} 提取。

        参数：
        - job_id：职位 ID。
        - org_id：组织标识；留空则使用 .env 中的 MOKA_ORG_ID。
        """
        enforce_tool("get_job_custom_fields")
        client = get_client()
        oid = _resolve_org_id(org_id)
        body = await client.get(f"/jobs/{oid}/{job_id}")
        custom_fields = body.get("customFields") if isinstance(body, dict) else None
        return {"jobId": job_id, "custom_fields": custom_fields}
