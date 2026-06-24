"""脱敏工具单元测试。"""

from __future__ import annotations

from moka_mcp.utils.sanitize import mask_id, mask_phone, sanitize


def test_mask_phone():
    assert mask_phone("13812341234") == "138****1234"


def test_mask_phone_short():
    assert mask_phone("123") == "****"


def test_mask_id():
    assert mask_id("410301199001012910") == "4103**********2910"


def test_sanitize_nested_dict():
    data = {
        "phone": "13812341234",
        "email": "a@b.com",
        "citizenId": "410301199001012910",
        "sub": {"mobile": "13800001111"},
    }
    out = sanitize(data, enabled=True)
    assert out["phone"] == "138****1234"
    assert out["email"] == "a@b.com"  # 邮箱默认不脱敏
    assert out["citizenId"] == "4103**********2910"
    assert out["sub"]["mobile"] == "138****1111"  # 嵌套同样生效


def test_sanitize_list():
    data = [{"phone": "13812341234"}, {"phone": "13900009999"}]
    out = sanitize(data, enabled=True)
    assert out[0]["phone"] == "138****1234"
    assert out[1]["phone"] == "139****9999"


def test_sanitize_disabled_returns_original():
    data = {"phone": "13812341234"}
    assert sanitize(data, enabled=False) == data


def test_sanitize_non_string_values_untouched():
    data = {"phone": None, "id": 123}
    out = sanitize(data, enabled=True)
    assert out == {"phone": None, "id": 123}
