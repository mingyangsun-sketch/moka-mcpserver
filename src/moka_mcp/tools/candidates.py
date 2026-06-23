"""候选人查询相关 Tool（第一阶段最高优先级模块）。

生产环境实测校准：
- 搜索/详情：GET v1 /data/ehrApplications，返回 {data, next, code, msg}。
- 申请记录：POST candidate/v1 /getApplicationStates，body {candidateId}。
- 候选人详情已自带 stageName，故 get_candidate_stage 直接从详情提取。
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import get_client
from ..errors import MokaEmptyStageError
from ..utils.pagination import fetch_all
from ..utils.sanitize import sanitize


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search_candidates(
        stage: Literal["offer", "pending_checkin", "all"] | None = None,
        email: str | None = None,
        phone: str | None = None,
        moved_at_start_time: str | None = None,
        moved_at_end_time: str | None = None,
        order: Literal["DESC", "ASC"] = "DESC",
        limit: int = 20,
    ) -> dict[str, Any]:
        """按条件搜索候选人（eHR 申请列表）。

        对应 Moka 接口：GET /data/ehrApplications（v1）

        参数说明：
        - stage：阶段筛选，offer=Offer 阶段 / pending_checkin=待入职 / all=两者。
        - email / phone：按邮箱或手机号精确筛选。
        - moved_at_start_time / moved_at_end_time：进入当前阶段的时间范围。
        - order：DESC（默认，从新到旧）/ ASC。
        - limit：返回条数上限（Moka 单页最大 20，这里支持跨页累计上限）。

        注意：stage 与 applicationId 至少需要一个定位条件；按 stage 查询且该
        阶段当前没有候选人时，Moka 会返回 500，本工具会将其作为「空结果」处理。
        """
        client = get_client()
        params = {
            "stage": stage,
            "email": email,
            "phone": phone,
            "movedAtStartTime": moved_at_start_time,
            "movedAtEndTime": moved_at_end_time,
            "order": order,
            "limit": min(limit, 20),
        }
        try:
            rows = await fetch_all(
                client,
                "/data/ehrApplications",
                params=params,
                max_items=limit,
                stage_query=stage is not None,
            )
        except MokaEmptyStageError:
            return {"total": 0, "candidates": [], "note": "该阶段当前没有候选人。"}

        masked = sanitize(rows, enabled=client.settings.mask_sensitive)
        return {"total": len(masked), "candidates": masked}

    @mcp.tool()
    async def get_candidate_detail(application_id: str) -> dict[str, Any]:
        """获取单个候选人的完整信息。

        对应 Moka 接口：GET /data/ehrApplications?applicationId={id}（v1）

        参数：
        - application_id：候选人申请 ID；支持逗号分隔的多个 ID（如 "81,82,83"）。

        返回包含基本信息、教育/工作经历、自定义字段、阶段、职位、Offer、
        面试官、内推人、附件等。注意附件与头像 URL 有效期仅 1 小时。
        """
        client = get_client()
        body = await client.get(
            "/data/ehrApplications",
            params={"applicationId": application_id},
        )
        data = body.get("data") if isinstance(body, dict) else body
        masked = sanitize(data, enabled=client.settings.mask_sensitive)
        return {"candidates": masked}

    @mcp.tool()
    async def get_candidate_applications(candidate_id: int) -> dict[str, Any]:
        """查询某候选人的所有申请记录及状态（一人可投递多个职位）。

        对应 Moka 接口：POST /getApplicationStates（candidate/v1，body 传 candidateId）

        参数：
        - candidate_id：候选人 ID（注意区别于 applicationId）。

        返回每条申请的 applicationId、status（in_progress/rejected 等）、
        stageName、createdAt。
        """
        client = get_client()
        body = await client.post(
            "/getApplicationStates",
            version="candidate/v1",
            json={"candidateId": candidate_id},
        )
        data = body.get("data") if isinstance(body, dict) else body
        return {"applications": data}

    @mcp.tool()
    async def get_candidate_stage(application_id: str) -> dict[str, Any]:
        """查询候选人当前所处的招聘阶段。

        实现说明：Moka v1 没有独立的单申请阶段查询接口，但候选人详情里自带
        stageName，故本工具复用 GET /data/ehrApplications?applicationId={id}。

        参数：
        - application_id：候选人申请 ID。
        """
        client = get_client()
        body = await client.get(
            "/data/ehrApplications",
            params={"applicationId": application_id},
        )
        data = body.get("data") if isinstance(body, dict) else body
        if not data:
            return {
                "applicationId": application_id,
                "stageName": None,
                "note": "未找到该申请。",
            }
        rec = data[0] if isinstance(data, list) else data
        return {
            "applicationId": rec.get("applicationId"),
            "candidateId": rec.get("candidateId"),
            "name": rec.get("name"),
            "stageName": rec.get("stageName"),
        }
