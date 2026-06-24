"""权限控制：工具级白名单 + 数据行级过滤。

stdio 模式下，每个被拉起的实例即「一个调用者」，其身份/角色由启动时注入的
env 决定（见 config.py）。因此这里以「单一 principal」模型实现，无需 HTTP 中间件。

安全前提：组织级 Moka Key 会随实例分发，故按用户限权只有在「可信后端
（如 Hermes）统一持有 Key 并为每个用户 spawn 对应角色的实例」时才真正有效。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
_ALL_TOOLS = (
    _CANDIDATE_TOOLS
    | _JOB_TOOLS
    | _PROCESS_TOOLS
    | _ORG_TOOLS
    | _OFFER_TOOLS
    | _TALENT_TOOLS
)

# 角色预设：可用工具 + 默认数据范围
# tools 为 "*" 表示全部
_ROLE_PRESETS: dict[str, dict] = {
    "admin": {"tools": "*", "scope": "all"},
    "hr_admin": {"tools": "*", "scope": "all"},
    "recruiter": {
        "tools": _CANDIDATE_TOOLS
        | _JOB_TOOLS
        | _PROCESS_TOOLS
        | _ORG_TOOLS
        | _OFFER_TOOLS
        | _TALENT_TOOLS,
        "scope": "owner",
    },
    "interviewer": {
        "tools": _CANDIDATE_TOOLS | _JOB_TOOLS | _PROCESS_TOOLS,
        "scope": "interviewer",
    },
    "hiring_manager": {
        "tools": _CANDIDATE_TOOLS | _JOB_TOOLS | _PROCESS_TOOLS | _ORG_TOOLS,
        "scope": "department",
    },
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
    scope: str  # all | interviewer | owner | department
    allowed_tools: frozenset[str]  # 空集且 allow_all=False 时表示无权限
    allow_all_tools: bool
    moka_user_id: int | None
    moka_email: str
    departments: tuple[str, ...]

    def can_use(self, tool_name: str) -> bool:
        return self.allow_all_tools or tool_name in self.allowed_tools


def _split_csv(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _build_principal(s: Settings) -> Principal:
    role = (s.role or "admin").strip().lower()
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
        moka_user_id=s.moka_user_id,
        moka_email=(s.moka_email or "").strip().lower(),
        departments=tuple(_split_csv(s.departments)),
    )


@lru_cache(maxsize=1)
def get_principal() -> Principal:
    return _build_principal(get_settings())


# ---------- 工具级控制 ----------

def enforce_tool(tool_name: str) -> None:
    """校验当前 principal 是否可调用该工具，不可则抛 PermissionError。"""
    p = get_principal()
    if not p.can_use(tool_name):
        raise ToolPermissionDenied(
            f"当前角色「{p.role}」无权调用工具 {tool_name}。"
            f"如需开通，请调整启动配置中的 MOKA_ROLE 或 MOKA_ALLOWED_TOOLS。"
        )


# ---------- 数据行级过滤 ----------

def _candidate_interviewer_ids(rec: dict) -> set[int]:
    ids: set[int] = set()
    for key in ("interviewers", "extendedInterviewers"):
        for iv in rec.get(key) or []:
            if isinstance(iv, dict) and isinstance(iv.get("id"), int):
                ids.add(iv["id"])
    return ids


def _candidate_owner_emails(rec: dict) -> set[str]:
    emails: set[str] = set()
    for key in ("owners", "jobManager"):
        v = rec.get(key)
        if isinstance(v, dict) and v.get("email"):
            emails.add(str(v["email"]).strip().lower())
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and item.get("email"):
                    emails.add(str(item["email"]).strip().lower())
    return emails


def _candidate_department(rec: dict) -> str | None:
    job = rec.get("job")
    if isinstance(job, dict):
        dep = job.get("department")
        if isinstance(dep, str):
            return dep
        if isinstance(dep, dict):
            return dep.get("name")
    return None


def filter_candidates(rows: list) -> list:
    """按当前 principal 的 scope 过滤候选人行。"""
    p = get_principal()
    if p.scope == "all" or not isinstance(rows, list):
        return rows

    out = []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        if p.scope == "interviewer":
            if p.moka_user_id is not None and p.moka_user_id in _candidate_interviewer_ids(rec):
                out.append(rec)
        elif p.scope == "owner":
            if p.moka_email and p.moka_email in _candidate_owner_emails(rec):
                out.append(rec)
        elif p.scope == "department":
            dep = _candidate_department(rec)
            if dep and dep in p.departments:
                out.append(rec)
        else:
            out.append(rec)
    return out


def _job_department_name(job: dict) -> str | None:
    dep = job.get("department")
    if isinstance(dep, str):
        return dep
    if isinstance(dep, dict):
        return dep.get("name")
    return None


def filter_jobs(rows: list) -> list:
    """按当前 principal 的 scope 过滤职位行。

    职位列表里只有部门可靠归属，故仅 department 范围会过滤；
    其余非 all 范围下职位敏感度较低，保持原样（访问与否由工具白名单控制）。
    """
    p = get_principal()
    if p.scope != "department" or not isinstance(rows, list):
        return rows
    return [
        j
        for j in rows
        if isinstance(j, dict) and _job_department_name(j) in p.departments
    ]
