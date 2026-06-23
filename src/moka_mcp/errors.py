"""统一错误处理：将 HTTP 异常转换为对 AI / 用户友好的错误信息。"""

from __future__ import annotations

import httpx

# HTTP 状态码 -> 友好提示（来自需求文档 5.4）
_STATUS_HINTS = {
    400: "请求参数有误，请检查 Tool 入参（例如 applicationId 与 stage 必须传其一）。",
    401: "认证失败：请检查 MOKA_API_KEY 是否正确、是否已失效。",
    403: "权限不足：该接口可能未对你的账号开通，请联系 Moka CSM 开通对应模块权限。",
    404: "资源不存在：对应的候选人 / 职位 / 资源未找到，请确认 ID 是否正确。",
    429: "触发频率限制：请稍后重试（Moka 部分接口有调用频率上限）。",
    500: "Moka 服务器异常。注意：按 stage 查询且该阶段当前没有候选人时，Moka 也会返回 500。",
}


class MokaError(Exception):
    """Moka API 调用相关的统一异常。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class MokaEmptyStageError(MokaError):
    """按 stage 查询时该阶段无候选人（Moka 返回 500）的特殊情形。"""


def raise_for_response(
    response: httpx.Response,
    *,
    stage_query: bool = False,
) -> None:
    """根据 HTTP 响应抛出友好的 MokaError；2xx 时不做任何处理。

    stage_query=True 表示本次是按 stage 查询候选人，遇到 500 时优先解释为
    "该阶段当前没有候选人"，避免误导。
    """
    if response.is_success:
        return

    status = response.status_code

    # 尝试提取 Moka 返回体里的错误信息
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = str(body.get("message") or body.get("error") or "")
    except Exception:
        detail = (response.text or "")[:500]

    hint = _STATUS_HINTS.get(status, f"请求失败（HTTP {status}）。")
    message = f"[Moka API 错误 {status}] {hint}"
    if detail:
        message += f"\n原始信息：{detail}"

    if status == 500 and stage_query:
        raise MokaEmptyStageError(
            "[Moka] 按 stage 查询返回 500：通常表示该阶段当前没有候选人，"
            "可视为空结果处理。",
            status_code=status,
        )

    raise MokaError(message, status_code=status)


# Moka 业务层「成功」的 code 取值：v1 用 0，v2 用 200
_SUCCESS_CODES = {0, 200}


def raise_for_body(body: object) -> None:
    """检测 HTTP 200 但业务层失败的响应（Moka 常以 code/success 表达逻辑错误）。

    - v1 形如 {"success": false, "code": 102, "msg": "参数错误"}
    - v2 形如 {"code": 200, "msg": "success"}（成功）
    列表 / 非 dict 响应不做校验。
    """
    if not isinstance(body, dict):
        return

    success = body.get("success")
    code = body.get("code")

    is_error = success is False or (
        success is None and code is not None and code not in _SUCCESS_CODES
    )
    if not is_error:
        return

    msg = body.get("msg") or body.get("errorMessage") or body.get("message") or ""
    raise MokaError(f"[Moka 业务错误 code={code}] {msg}".strip())
