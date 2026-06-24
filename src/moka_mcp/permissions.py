"""权限控制：工具级白名单 + 数据行级过滤（面向企业内部用户）。

身份模型（模型 A）：Hermes 解析 Slack 用户 → 决定角色/部门 → 用对应 env 拉起
该用户的 MCP 实例。因此每个实例即「一个调用者」，其角色由启动 env 决定，
MCP 侧以「单一 principal」实现，无需 HTTP 中间件 / 每请求身份。

安全前提：组织级 Moka Key 会随实例分发，故按用户限权只有在「可信后端
（Hermes）统一持有 Key 并为每个用户 spawn 对应角色的实例」时才真正有效。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .config import Settings, get_settings

# 工具分组
_CANDIDATE_TOOLS = {
    "search_candidates",
    "get_candidate_detail",
    "get_candidate_stage",
    "get_candidate_applications",
}
_JOB_TOOLS = {"list_jobs", "get_job_detail", "get_job_custom_fields"}
_PROCESS_TOOLS = {"list_pipelines", "list_stages"}
_ORG_TOOLS = {"list_departments"}
_OFFER_TOOLS = {"get_offer_custom_fields"}
_TALENT_TOOLS = {"list_talent_pools", "list_talent_pool_candidates"}

# 角色预设（面向内部用户）：可用工具 + 默认数据范围
# tools 为 "*" 表示全部；scope ∈ {all, department}
_ROLE_PRESETS: dict[str, dict] = {
    # HR/招聘团队负责人：全部工具 + 全量数据
    "hr_admin": {"tools": "*", "scope": "all"},
    "admin": {"tools": "*", "scope": "all"},  # 别名/兜底
    # 招聘专员：候选人/职位/流程/Offer/人才库/组织（读），全量
    "recruiter": {
        "tools": _CANDIDATE_TOOLS
        | _JOB_TOOLS
        | _PROCESS_TOOLS
        | _OFFER_TOOLS
        | _TALENT_TOOLS
        | _ORG_TOOLS,
        "scope": "all",
    },
    # 用人经理/部门负责人：候选人/职位/流程/组织（读，无人才库），仅本部门
    "hiring_manager": {
        "tools": _CANDIDATE_TOOLS | _JOB_TOOLS | _PROCESS_TOOLS | _ORG_TOOLS,
        "scope": "department",
    },
    # 普通员工：职位/流程/组织等公开信息，不含候选人 PII
    "viewer": {
        "tools": _JOB_TOOLS | _PROCESS_TOOLS | _ORG_TOOLS,
        "scope": "all",
    },
}


class ToolPermissionDenied(Exception):
    """权限不足（工具未授权）。"""


@dataclass(frozen=True)
class Principal:
    role: str
    scope: str  # all | department
    allowed_tools: frozenset[str]
    allow_all_tools: bool
    departments: tuple[str, ...]

    def can_use(self, tool_name: str) -> bool:
        return self.allow_all_tools or tool_name in self.allowed_tools


def _split_csv(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _build_principal(s: Settings) -> Principal:
    role = (s.role or "hr_admin").strip().lower()
    preset = _ROLE_PRESETS.get(role, _ROLE_PRESETS["viewer"])

    # 工具白名单：env 覆盖优先，否则用角色预设
    if s.allowed_tools.strip():
        items = _split_csv(s.allowed_tools)
        allow_all = "*" in items
        tools = frozenset(t for t in items if t != "*")
    else:
        preset_tools = preset["tools"]
        allow_all = preset_tools == "*"
        tools = frozenset() if allow_all else frozenset(preset_tools)

    scope = (s.scope or preset["scope"]).strip().lower()

    return Principal(
        role=role,
        scope=scope,
        allowed_tools=tools,
        allow_all_tools=allow_all,
        departments=tuple(_split_csv(s.departments)),
    )


@lru_cache(maxsize=1)
def get_principal() -> Principal:
    return _build_principal(get_settings())


# ---------- 工具级控制 ----------

def enforce_tool(tool_name: str) -> None:
    """校验当前 principal 是否可调用该工具，不可则抛 ToolPermissionDenied。"""
    p = get_principal()
    if not p.can_use(tool_name):
        raise ToolPermissionDenied(
            f"当前角色「{p.role}」无权调用工具 {tool_name}。"
            f"如需开通，请调整启动配置中的 MOKA_ROLE 或 MOKA_ALLOWED_TOOLS。"
        )


# ---------- 数据行级过滤（按部门）----------

def _candidate_department(rec: dict) -> str | None:
    job = rec.get("job")
    if isinstance(job, dict):
        dep = job.get("department")
        if isinstance(dep, str):
            return dep
        if isinstance(dep, dict):
            return dep.get("name")
    return None


def _norm(name: str | None) -> str:
    return (name or "").strip()


def filter_candidates(rows: list) -> list:
    """按当前 principal 的 scope 过滤候选人行（仅 department 范围会过滤）。"""
    p = get_principal()
    if p.scope != "department" or not isinstance(rows, list):
        return rows
    # 两侧均 trim 后比较（Moka 部门名可能带尾随空格）
    depts = {_norm(d) for d in p.departments}
    return [
        rec
        for rec in rows
        if isinstance(rec, dict) and _norm(_candidate_department(rec)) in depts
    ]


def _job_department_name(job: dict) -> str | None:
    dep = job.get("department")
    if isinstance(dep, str):
        return dep
    if isinstance(dep, dict):
        return dep.get("name")
    return None


def filter_jobs(rows: list) -> list:
    """按当前 principal 的 scope 过滤职位行（仅 department 范围会过滤）。"""
    p = get_principal()
    if p.scope != "department" or not isinstance(rows, list):
        return rows
    depts = {_norm(d) for d in p.departments}
    return [
        j
        for j in rows
        if isinstance(j, dict) and _norm(_job_department_name(j)) in depts
    ]
