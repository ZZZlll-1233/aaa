"""业务层测试：不起服务，直接调函数。

这层测的是「入参校验 + 业务语义」，速度是毫秒级。
"""

from __future__ import annotations

import pytest

from pystrkit_web.api import batch, invoke
from pystrkit_web.errors import BadRequest, InvalidArgument


def test_text_width() -> None:
    data = invoke("text.width", {"text": "中文abc"})
    assert data["width"] == 7  # 2+2+3
    assert data["length"] == 5


def test_text_count() -> None:
    data = invoke("text.count", {"text": "Python 是最好的语言"})
    assert data["words"] == 7
    assert data["chars"] == len("Python 是最好的语言")


def test_text_truncate_keeps_width_contract() -> None:
    data = invoke("text.truncate", {"text": "中文文本处理工具库", "width": 6})
    assert data["result"] == "中文…"
    assert data["result_width"] <= 6
    assert data["truncated"] is True


def test_text_truncate_no_truncate_when_short() -> None:
    data = invoke("text.truncate", {"text": "短", "width": 50})
    assert data["result"] == "短"
    assert data["truncated"] is False


def test_text_slug() -> None:
    data = invoke("text.slug", {"text": "Hello, Gitee! 开源 项目"})
    assert data["result"] == "hello-gitee"


def test_mask_phone() -> None:
    data = invoke("mask.phone", {"value": "13812345678"})
    assert data["result"] == "138****5678"
    assert data["valid"] is True


def test_mask_phone_invalid_returns_as_is() -> None:
    """非法号码原样返回，且不抛异常——这是库的既定取舍。"""
    data = invoke("mask.phone", {"value": "12345"})
    assert data["result"] == "12345"
    assert data["valid"] is False


def test_mask_id_card_keeps_x() -> None:
    data = invoke("mask.id-card", {"value": "11010119900307123X"})
    assert data["result"] == "110101********123X"


def test_mask_scan_order_matters() -> None:
    """先身份证后手机号，否则 18 位里的 11 位数字会被手机号规则截断。"""
    text = "用户 13812345678，身份证 110101199003071234"
    data = invoke("mask.scan", {"text": text})
    assert data["phone_count"] == 1
    assert data["id_card_count"] == 1
    assert data["total"] == 2
    assert "138****5678" in data["result"]
    assert "110101********1234" in data["result"]


def test_money_rmb() -> None:
    assert invoke("money.rmb", {"amount": "1234.56"})["result"] == "壹仟贰佰叁拾肆元伍角陆分"
    assert invoke("money.rmb", {"amount": "1.05"})["result"] == "壹元零伍分"
    assert invoke("money.rmb", {"amount": "100"})["result"] == "壹佰元整"


def test_money_rmb_invalid_raises_business_error() -> None:
    """金额解析失败必须抛错，且要转成 InvalidArgument 而不是裸 ValueError。"""
    with pytest.raises(InvalidArgument):
        invoke("money.rmb", {"amount": "abc"})


def test_missing_param() -> None:
    with pytest.raises(BadRequest, match="缺少必填参数"):
        invoke("money.rmb", {})


def test_wrong_type() -> None:
    with pytest.raises(BadRequest, match="必须是字符串"):
        invoke("text.width", {"text": 123})


def test_int_param_out_of_range() -> None:
    with pytest.raises(BadRequest, match="需在"):
        invoke("text.truncate", {"text": "abc", "width": 99999})


def test_unknown_endpoint() -> None:
    with pytest.raises(BadRequest, match="未知接口"):
        invoke("nope.nope", {})


def test_batch_continues_on_failure() -> None:
    """单行脏数据不该让整批白干。"""
    data = invoke("batch", {"fn": "rmb", "text": "1.05\n不是金额\n100"})
    assert data["total"] == 3
    assert data["failed"] == 1
    assert data["items"][0]["output"] == "壹元零伍分"
    assert data["items"][1]["ok"] is False
    assert data["items"][1]["error"]
    assert data["items"][2]["output"] == "壹佰元整"


def test_batch_phone() -> None:
    data = invoke("batch", {"fn": "phone", "text": "13812345678\n12345"})
    assert data["items"][0]["output"] == "138****5678"
    # 非法号码原样返回，不算失败——脱敏本来就承诺不抛异常
    assert data["items"][1]["output"] == "12345"


def test_batch_unknown_fn() -> None:
    with pytest.raises(BadRequest, match="未知的批量函数"):
        invoke("batch", {"fn": "nope", "text": "a"})


def test_batch_all_functions_runnable() -> None:
    """防止新增函数忘了在 _single 里实现。"""
    for fn in ("phone", "id-card", "rmb", "slug", "count", "width", "truncate", "scan"):
        data = batch({"fn": fn, "text": "13812345678"})
        assert data["total"] == 1
        assert data["items"][0]["ok"] is True


def test_batch_respects_options() -> None:
    data = invoke(
        "batch", {"fn": "truncate", "text": "中文文本处理工具库", "options": {"width": 6}}
    )
    assert data["items"][0]["output"] == "中文…"
