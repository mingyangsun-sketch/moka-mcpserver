"""Moka HTTP 客户端封装：Basic Auth、多版本路由、统一错误处理、轻量重试。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .config import Settings, get_settings
from .errors import MokaError, raise_for_body, raise_for_response

# 429（频率限制）时的重试配置
_RETRY_STATUS = {429}
_MAX_RETRIES = 2
_RETRY_BACKOFF = 1.5  # 秒，指数退避基数


class MokaClient:
    """对 Moka API 的薄封装，支持 v1 / v2 / candidate/v1 多套基础路径。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=httpx.BasicAuth(self._settings.api_key, ""),
                headers={"Accept": "application/json"},
                timeout=self._settings.timeout,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _url(self, path: str, version: str) -> str:
        return f"{self._settings.api_base(version)}{path}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        stage_query: bool = False,
    ) -> Any:
        """发起请求并返回解析后的 JSON。

        - version：v1 / v2 / candidate/v1，决定基础路径。
        - params：query 参数（自动过滤 None）。
        - json：POST body。
        - stage_query：透传给错误处理，区分 stage 查无人时的 500。
        """
        client = self._ensure_client()
        url = self._url(path, version)
        clean_params = (
            {k: v for k, v in params.items() if v is not None} if params else None
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await client.request(
                    method, url, params=clean_params, json=json
                )
            except httpx.RequestError as exc:
                last_exc = MokaError(f"[Moka] 网络请求失败：{exc}")
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                raise last_exc from exc

            if response.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
                continue

            raise_for_response(response, stage_query=stage_query)
            body = response.json()
            raise_for_body(body)
            return body

        if last_exc:
            raise last_exc
        raise MokaError("[Moka] 请求失败：超过最大重试次数。")

    async def get(
        self,
        path: str,
        *,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        stage_query: bool = False,
    ) -> Any:
        return await self.request(
            "GET", path, version=version, params=params, stage_query=stage_query
        )

    async def post(
        self,
        path: str,
        *,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        return await self.request(
            "POST", path, version=version, params=params, json=json
        )


# 模块级单例，供各 Tool 复用
_client: MokaClient | None = None


def get_client() -> MokaClient:
    global _client
    if _client is None:
        _client = MokaClient()
    return _client
