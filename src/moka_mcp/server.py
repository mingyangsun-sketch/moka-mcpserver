"""Moka MCP Server 入口：创建 FastMCP 实例并注册所有 Tool。

支持两种传输方式（由 MOKA_TRANSPORT 控制）：
- stdio：本地子进程方式（Claude Desktop / Cursor 等默认）。
- http ：自托管 streamable-http 端点（如 http://host:port/mcp），供 Hermes
         等 agent 通过 baseUrl + Bearer Token 接入（mcporter 模板 B / http_bearer）。
"""

from __future__ import annotations

import hmac

from mcp.server.fastmcp import FastMCP

from .config import get_settings
from .tools import register_all

_settings = get_settings()

# FastMCP 实例：name 会展示在 MCP 客户端里
mcp = FastMCP(
    "moka-mcp-server",
    instructions=(
        "Moka HR 招聘系统 MCP Server（第一阶段：只读）。"
        "提供候选人、职位、招聘流程、组织架构、Offer 字段、人才库等查询能力。"
        "敏感字段（手机号/身份证）默认脱敏。所有写入类操作均未开放。"
    ),
    host=_settings.http_host,
    port=_settings.http_port,
    streamable_http_path=_settings.http_path,
)

register_all(mcp)


def _build_http_app():
    """构造带 X-API-Key 鉴权的 streamable-http ASGI 应用。"""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    api_key = _settings.mcp_api_key

    class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if api_key:
                provided = request.headers.get("x-api-key", "")
                # 常量时间比较，避免时序侧信道
                if not hmac.compare_digest(provided, api_key):
                    return JSONResponse(
                        {"error": "unauthorized", "message": "缺少或无效的 X-API-Key"},
                        status_code=401,
                    )
            return await call_next(request)

    app = mcp.streamable_http_app()
    app.add_middleware(ApiKeyAuthMiddleware)
    return app


def main() -> None:
    """根据 MOKA_TRANSPORT 选择运行方式。"""
    if _settings.transport == "http":
        import uvicorn

        uvicorn.run(
            _build_http_app(),
            host=_settings.http_host,
            port=_settings.http_port,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
