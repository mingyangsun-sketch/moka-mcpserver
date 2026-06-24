"""Moka 用户目录：按邮箱解析 Moka 用户（userId / 角色 / 部门），供权限派生使用。

数据来源（均用组织级 key 调用）：
- POST /users/list           人事信息（含 email / userId / role / department），next 游标分页
- GET  /users/roles?type=all 角色字典（role int -> 角色名）

注意：解析用的 email 必须是可信来源（Hermes 校验过的 Slack 邮箱），
不能是 LLM/用户随意填入，否则可被冒充。
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import get_client

_PAGE_LIMIT = 100


@dataclass(frozen=True)
class MokaUser:
    user_id: int | None
    email: str
    name: str
    role: int | None
    role_name: str
    departments: tuple[str, ...]
    deactivated: int


class MokaDirectory:
    """用户目录：按邮箱服务端精确查询 Moka 用户（带进程内缓存）。

    /users/list 支持 body 传 email 做服务端过滤，故单次精确查询即可，
    无需拉取全量用户。
    """

    def __init__(self) -> None:
        self._roles: dict[int, str] | None = None
        self._cache: dict[str, MokaUser | None] = {}

    async def _load_roles(self) -> dict[int, str]:
        if self._roles is None:
            body = await get_client().get("/users/roles", params={"type": "all"})
            data = body.get("data") if isinstance(body, dict) else []
            roles: dict[int, str] = {}
            for r in data or []:
                ri = r.get("role")
                if ri is not None and ri not in roles:
                    roles[ri] = r.get("name") or ""
            self._roles = roles
        return self._roles

    @staticmethod
    def _to_user(u: dict, roles: dict[int, str]) -> MokaUser:
        deps = tuple(
            (d.get("name") if isinstance(d, dict) else d)
            for d in (u.get("department") or [])
            if d
        )
        return MokaUser(
            user_id=u.get("userId"),
            email=(u.get("email") or "").strip().lower(),
            name=u.get("name") or "",
            role=u.get("role"),
            role_name=roles.get(u.get("role"), ""),
            departments=tuple(d for d in deps if d),
            deactivated=u.get("deactivated", 0),
        )

    async def resolve(self, email: str) -> MokaUser | None:
        """按邮箱精确解析 Moka 用户；未找到返回 None（结果缓存）。"""
        key = (email or "").strip().lower()
        if not key:
            return None
        if key in self._cache:
            return self._cache[key]

        roles = await self._load_roles()
        resp = await get_client().post(
            "/users/list",
            json={"deactivated": 0, "limit": str(_PAGE_LIMIT), "order": "asc", "email": email},
        )
        rows = resp.get("data") if isinstance(resp, dict) else []
        # email 过滤可能是模糊匹配，这里严格按完整邮箱命中
        match = next(
            (u for u in (rows or []) if (u.get("email") or "").strip().lower() == key),
            None,
        )
        user = self._to_user(match, roles) if match else None
        self._cache[key] = user
        return user


_directory: MokaDirectory | None = None


def get_directory() -> MokaDirectory:
    global _directory
    if _directory is None:
        _directory = MokaDirectory()
    return _directory
