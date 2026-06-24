"""配置管理：从环境变量 / .env 读取 Moka MCP Server 配置。

Moka API 实测涉及三套基础路径（同一 host 下）：
  - v1          : {host}/api-platform/v1          （多数接口）
  - v2          : {host}/api-platform/v2          （招聘流程、阶段）
  - candidate/v1: {host}/api-platform/candidate/v1（候选人申请记录等）
本模块按「host + 版本段」拼接最终 URL。
"""

from __future__ import annotations

import base64
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 不同环境的 host（来自需求文档 2.3，实测中国版生产可用）
_HOSTS = {
    "production": "https://api.mokahr.com",
    "staging": "https://api-staging-3.mokahr.com",
}


class Settings(BaseSettings):
    """Moka MCP Server 运行配置。"""

    model_config = SettingsConfigDict(
        env_prefix="MOKA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(..., description="Moka API Key（Basic Auth），由 CSM 发放")
    org_id: str = Field("", description="组织标识，职位类接口需要")
    env: str = Field("production", description="运行环境：production | staging")
    base_url: str | None = Field(
        None, description="显式覆盖 host（如 https://api.mokahr.com），一般留空"
    )
    mask_sensitive: bool = Field(True, description="是否对手机号/身份证等敏感字段脱敏")
    timeout: float = Field(30.0, description="HTTP 请求超时（秒）")
    max_items: int = Field(200, description="自动翻页最多拉取条数上限")

    # ===== 权限控制（stdio 单实例 = 单一调用者身份，由启动 env 注入）=====
    role: str = Field(
        "admin",
        description="调用者角色：admin/hr_admin | recruiter | interviewer | "
        "hiring_manager | viewer。决定可用工具与默认数据范围",
    )
    moka_user_id: int | None = Field(
        None, description="调用者对应的 Moka 用户 id（int），用于 interviewer 范围过滤"
    )
    moka_email: str = Field(
        "", description="调用者对应的 Moka 邮箱，用于 owner 范围过滤"
    )
    departments: str = Field(
        "", description="逗号分隔的部门名列表，用于 department 范围过滤"
    )
    scope: str = Field(
        "",
        description="数据范围覆盖：all | interviewer | owner | department；留空则按 role 推断",
    )
    allowed_tools: str = Field(
        "",
        description="逗号分隔的工具白名单覆盖；留空则按 role 推断。* 表示全部",
    )

    # ===== MCP Server 自身的传输/部署配置 =====
    transport: str = Field(
        "stdio", description="MCP 传输方式：stdio（本地）| http（自托管 HTTP 端点）"
    )
    http_host: str = Field("0.0.0.0", description="http 传输时监听地址")
    http_port: int = Field(8000, description="http 传输时监听端口")
    http_path: str = Field("/mcp", description="http 传输时 MCP 端点路径")
    mcp_api_key: str = Field(
        "",
        description="http 传输时要求的访问密钥（agent 须在 X-API-Key 头携带）；"
        "留空表示不校验（仅限可信内网）。注意与 MOKA_API_KEY（访问 Moka 用）区分",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def host(self) -> str:
        """最终生效的 host（scheme://netloc，不含 /api-platform 路径）。"""
        if self.base_url:
            parsed = urlparse(self.base_url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
            return self.base_url.rstrip("/")
        return _HOSTS.get(self.env, _HOSTS["production"])

    def api_base(self, version: str = "v1") -> str:
        """按版本段拼接基础路径，如 api_base('v2') -> {host}/api-platform/v2。"""
        return f"{self.host}/api-platform/{version}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_base_url(self) -> str:
        """默认 v1 基础路径（向后兼容）。"""
        return self.api_base("v1")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def auth_header(self) -> str:
        """Basic Auth 头部值：Basic base64(api_key + ":")。"""
        token = base64.b64encode(f"{self.api_key}:".encode("utf-8")).decode("ascii")
        return f"Basic {token}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回单例配置对象（首次调用时从环境加载）。"""
    return Settings()  # type: ignore[call-arg]
