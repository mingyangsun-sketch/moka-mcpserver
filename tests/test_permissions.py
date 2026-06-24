"""权限层单元测试：角色预设、工具白名单、部门行级过滤（含 trim）。"""

from __future__ import annotations

import pytest

from moka_mcp import permissions
from moka_mcp.config import Settings
from moka_mcp.permissions import (
    Principal,
    ToolPermissionDenied,
    _build_principal,
    enforce_tool,
    filter_candidates,
    filter_jobs,
)


def mk(role="hr_admin", scope="", allowed_tools="", departments="") -> Principal:
    """用显式配置构造 principal（显式 kwarg 优先于 .env / 环境变量）。"""
    s = Settings(
        api_key="x",
        role=role,
        scope=scope,
        allowed_tools=allowed_tools,
        departments=departments,
    )
    return _build_principal(s)


# ---------- 角色预设 ----------

def test_hr_admin_all_tools():
    p = mk("hr_admin")
    assert p.allow_all_tools is True
    assert p.can_use("any_future_tool")
    assert p.scope == "all"


def test_admin_alias_equals_hr_admin():
    assert mk("admin").allow_all_tools is True


def test_recruiter_full_read():
    p = mk("recruiter")
    for t in (
        "search_candidates",
        "get_candidate_detail",
        "list_jobs",
        "list_talent_pools",
        "get_offer_custom_fields",
        "list_departments",
    ):
        assert p.can_use(t), t
    assert p.scope == "all"


def test_hiring_manager_scope_and_tools():
    p = mk("hiring_manager", departments="产品部,技术部")
    assert p.scope == "department"
    assert p.can_use("search_candidates")
    assert p.can_use("list_jobs")
    assert not p.can_use("list_talent_pools")  # 无人才库
    assert p.departments == ("产品部", "技术部")


def test_viewer_no_candidate_pii():
    p = mk("viewer")
    assert not p.can_use("search_candidates")
    assert not p.can_use("get_candidate_detail")
    assert not p.can_use("list_talent_pools")
    assert p.can_use("list_jobs")
    assert p.can_use("list_pipelines")
    assert p.can_use("list_departments")


def test_unknown_role_falls_back_to_viewer():
    p = mk("nonsense_role")
    assert not p.can_use("search_candidates")
    assert p.can_use("list_jobs")


# ---------- 覆盖项 ----------

def test_allowed_tools_override_whitelist():
    p = mk("viewer", allowed_tools="search_candidates,list_jobs")
    assert p.can_use("search_candidates")  # 覆盖放开
    assert p.can_use("list_jobs")
    assert not p.can_use("list_pipelines")  # 不在白名单


def test_allowed_tools_wildcard():
    p = mk("viewer", allowed_tools="*")
    assert p.allow_all_tools is True


def test_scope_override():
    assert mk("recruiter", scope="department").scope == "department"


# ---------- enforce_tool ----------

def test_enforce_tool_raises_for_denied(monkeypatch):
    monkeypatch.setattr(permissions, "get_principal", lambda: mk("viewer"))
    with pytest.raises(ToolPermissionDenied):
        enforce_tool("search_candidates")
    enforce_tool("list_jobs")  # 允许的工具不抛异常


# ---------- 数据行级过滤 ----------

_CANDS = [
    {"name": "a", "job": {"department": "产品部"}},
    {"name": "b", "job": {"department": "技术部 "}},  # 尾随空格
    {"name": "c", "job": {"department": "销售部"}},
    {"name": "d", "job": {}},  # 无部门
]


def _principal(scope, departments=(), allow_all=True):
    return Principal(
        role="test",
        scope=scope,
        allowed_tools=frozenset(),
        allow_all_tools=allow_all,
        departments=tuple(departments),
    )


def test_filter_candidates_department_with_trim(monkeypatch):
    monkeypatch.setattr(
        permissions, "get_principal",
        lambda: _principal("department", ("产品部", "技术部")),
    )
    out = filter_candidates(_CANDS)
    assert {c["name"] for c in out} == {"a", "b"}  # b 经 trim 命中


def test_filter_candidates_scope_all_no_filter(monkeypatch):
    monkeypatch.setattr(permissions, "get_principal", lambda: _principal("all"))
    assert filter_candidates(_CANDS) == _CANDS


def test_filter_candidates_no_match(monkeypatch):
    monkeypatch.setattr(
        permissions, "get_principal", lambda: _principal("department", ("不存在",))
    )
    assert filter_candidates(_CANDS) == []


_JOBS = [
    {"id": 1, "department": {"name": "产品部"}},
    {"id": 2, "department": {"name": "销售部"}},
    {"id": 3, "department": "产品部 "},  # 字符串形式 + 尾随空格
]


def test_filter_jobs_department(monkeypatch):
    monkeypatch.setattr(
        permissions, "get_principal", lambda: _principal("department", ("产品部",))
    )
    out = filter_jobs(_JOBS)
    assert [j["id"] for j in out] == [1, 3]


def test_filter_jobs_scope_all_no_filter(monkeypatch):
    monkeypatch.setattr(permissions, "get_principal", lambda: _principal("all"))
    assert filter_jobs(_JOBS) == _JOBS


# ---------- 由 Moka role 派生角色档 ----------

def test_tier_for_moka_role():
    f = permissions._tier_for_moka_role
    assert f(50) == "hr_admin"  # 超级管理员
    assert f(40) == "hr_admin"  # 管理员
    assert f(30) == "hr_admin"  # HR
    assert f(25) == "hiring_manager"  # 高级用人经理
    assert f(20) == "hiring_manager"  # 用人经理
    assert f(10) == "interviewer"  # 面试官
    assert f(5) == "viewer"  # 前台
    assert f(0) == "viewer"  # 内推人
    assert f(None) == "viewer"


def test_principal_for_tier_hr_admin():
    p = permissions._principal_for_tier("hr_admin", ())
    assert p.allow_all_tools
    assert p.scope == "all"


def test_principal_for_tier_hiring_manager_keeps_departments():
    p = permissions._principal_for_tier("hiring_manager", ("产品部 ", "技术部"))
    assert p.scope == "department"
    assert p.departments == ("产品部", "技术部")  # 已 trim
    assert p.can_use("search_candidates")
    assert not p.can_use("list_talent_pools")


def test_interviewer_tier_tools_and_scope():
    p = permissions._principal_for_tier("interviewer", (), moka_user_id=4242)
    assert p.scope == "interviewer"
    assert p.moka_user_id == 4242
    # 可看候选人状态/详情/阶段 + 职位/流程
    assert p.can_use("search_candidates")
    assert p.can_use("get_candidate_detail")
    assert p.can_use("get_candidate_stage")
    assert p.can_use("list_jobs")
    # 不可：按 candidateId 查申请、人才库、Offer 字段
    assert not p.can_use("get_candidate_applications")
    assert not p.can_use("list_talent_pools")
    assert not p.can_use("get_offer_custom_fields")


_CANDS_IV = [
    {"name": "x", "interviewers": [{"id": 11}, {"id": 22}]},
    {"name": "y", "interviewers": [{"id": 33}]},
    {"name": "z", "extendedInterviewers": [{"id": 22}]},
    {"name": "w", "interviewers": []},
]


def test_filter_candidates_interviewer_scope(monkeypatch):
    pr = Principal("interviewer", "interviewer", frozenset(), False, (), moka_user_id=22)
    monkeypatch.setattr(permissions, "get_principal", lambda: pr)
    monkeypatch.setattr(permissions, "_resolved", pr, raising=False)
    out = filter_candidates(_CANDS_IV)
    assert {c["name"] for c in out} == {"x", "z"}  # 22 在 x 和 z


def test_filter_candidates_interviewer_no_user_id_returns_empty(monkeypatch):
    pr = Principal("interviewer", "interviewer", frozenset(), False, (), moka_user_id=None)
    monkeypatch.setattr(permissions, "_resolved", pr, raising=False)
    assert filter_candidates(_CANDS_IV) == []
