"""数据脱敏：对手机号、身份证等敏感字段做掩码处理。

脱敏规则来自需求文档 5.5：
    phone     -> 138****1234
    citizenId -> 4103**********2910
默认对 email 不脱敏。
"""

from __future__ import annotations

from typing import Any

# 需要脱敏的字段名（兼容 Moka 常见命名）
_PHONE_KEYS = {"phone", "mobile", "telephone", "phoneNumber"}
_ID_KEYS = {"citizenId", "idCard", "idNumber", "identityCard"}


def mask_phone(value: str) -> str:
    """手机号脱敏：保留前 3 位与后 4 位，中间用 **** 替换。"""
    digits = value.strip()
    if len(digits) <= 7:
        return "****"
    return f"{digits[:3]}****{digits[-4:]}"


def mask_id(value: str) -> str:
    """身份证脱敏：保留前 4 位与后 4 位，中间掩码。"""
    s = value.strip()
    if len(s) <= 8:
        return "****"
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


def _mask_value(key: str, value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if key in _PHONE_KEYS:
        return mask_phone(value)
    if key in _ID_KEYS:
        return mask_id(value)
    return value


def sanitize(obj: Any, *, enabled: bool = True) -> Any:
    """递归脱敏任意 JSON 结构（dict/list）。enabled=False 时原样返回。"""
    if not enabled:
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(_mask_value(k, v), enabled=enabled) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(item, enabled=enabled) for item in obj]
    return obj
