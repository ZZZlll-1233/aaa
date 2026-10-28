"""业务逻辑层：每个函数都是「dict 进、dict 出」，不依赖 HTTP。

这样写的好处是测试不用起服务——直接 `invoke("money.rmb", {"amount": "1.05"})`
就能断言。HTTP 层只负责搬砖。

同时这一层承担两件事：
1. 入参校验与类型转换（前端传来的全是字符串，需要转成 int）
2. 把 pystrkit 抛的 ValueError 转成 InvalidArgument，带上「哪个字段错了」
"""

from __future__ import annotations

import re
from typing import Any, Callable

from pystrkit import (
    count_words,
    display_width,
    mask_id_card,
    mask_phone,
    to_rmb_upper,
    to_slug,
    truncate_by_width,
)

from .errors import BadRequest, InvalidArgument

# ---------------------------------------------------------------------------
# 全文扫描用的正则
#
# 注意这里和 pystrkit 内部的正则不是一回事：
#   库里的是 ^...$ 全匹配，用于「这个值是不是一个合法手机号」的判定；
#   这里是搜索模式，用于在一段正文里捞出所有像手机号的子串。
# 搜索必须宽松（否则正文里带分隔符的号码会被漏掉），
# 脱敏必须严格（否则把订单号之类的数字串也打上星号）。
# ---------------------------------------------------------------------------
_PHONE_SCAN_RE = re.compile(r"1[3-9]\d{9}")
_ID_SCAN_RE = re.compile(r"\d{17}[\dXx]")

_MAX_BATCH_LINES = 5000
_MAX_TEXT_LEN = 200_000


# ---------------------------------------------------------------------------
# 取参工具
# ---------------------------------------------------------------------------
def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise BadRequest(f"缺少必填参数：{key}")
    return payload[key]


def _as_text(payload: dict[str, Any], key: str) -> str:
    value = _require(payload, key)
    if not isinstance(value, str):
        raise BadRequest(f"参数 {key} 必须是字符串")
    if len(value) > _MAX_TEXT_LEN:
        raise BadRequest(f"参数 {key} 过长（上限 {_MAX_TEXT_LEN} 字符）")
    return value


def _as_int(
    payload: dict[str, Any],
    key: str,
    default: int,
    minimum: int = 0,
    maximum: int = 10_000,
) -> int:
    if key not in payload or payload[key] in (None, ""):
        return default
    raw = payload[key]
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise BadRequest(f"参数 {key} 必须是整数，收到 {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise BadRequest(f"参数 {key} 需在 {minimum}~{maximum} 之间，收到 {value}")
    return value


def _as_amount(payload: dict[str, Any], key: str = "amount") -> Any:
    """金额入参原样透传给 Decimal。

    刻意不在这里做 float 转换：pystrkit 内部用 ``Decimal(str(amount))``，
    传字符串进去才能完全避开 0.1 + 0.2 那类浮点误差。
    """
    value = _require(payload, key)
    if isinstance(value, bool) or value is None:
        raise BadRequest(f"参数 {key} 不能为空")
    if not isinstance(value, (str, int, float)):
        raise BadRequest(f"参数 {key} 必须是字符串或数字")
    return value


def _call(fn: Callable[..., Any], *args: Any, field: str) -> Any:
    """执行库函数，把 ValueError 转成带字段信息的业务错误。"""
    try:
        return fn(*args)
    except ValueError as exc:
        raise InvalidArgument(str(exc), detail=f"出错字段：{field}") from exc


# ---------------------------------------------------------------------------
# 各接口实现
# ---------------------------------------------------------------------------
def text_width(payload: dict[str, Any]) -> dict[str, Any]:
    text = _as_text(payload, "text")
    return {
        "text": text,
        "width": display_width(text),
        "length": len(text),
    }


def text_count(payload: dict[str, Any]) -> dict[str, Any]:
    text = _as_text(payload, "text")
    return {
        "text": text,
        "words": count_words(text),
        "chars": len(text),
        "width": display_width(text),
    }


def text_truncate(payload: dict[str, Any]) -> dict[str, Any]:
    text = _as_text(payload, "text")
    width = _as_int(payload, "width", 20, minimum=1, maximum=10_000)
    suffix = payload.get("suffix", "…")
    if not isinstance(suffix, str):
        raise BadRequest("参数 suffix 必须是字符串")

    result = truncate_by_width(text, width, suffix)
    return {
        "text": text,
        "result": result,
        "width": width,
        "result_width": display_width(result),
        "truncated": result != text,
    }


def text_slug(payload: dict[str, Any]) -> dict[str, Any]:
    text = _as_text(payload, "text")
    max_length = _as_int(payload, "max_length", 60, minimum=1, maximum=200)
    return {
        "text": text,
        "result": to_slug(text, max_length),
        "max_length": max_length,
    }


def mask_phone_api(payload: dict[str, Any]) -> dict[str, Any]:
    value = _as_text(payload, "value")
    keep_head = _as_int(payload, "keep_head", 3, minimum=0, maximum=18)
    keep_tail = _as_int(payload, "keep_tail", 4, minimum=0, maximum=18)
    result = mask_phone(value, keep_head, keep_tail)
    return {
        "value": value,
        "result": result,
        "masked": result != value,
        # 脱敏是「尽力而为」：格式不合法时原样返回而不是报错，
        # 所以这里必须告诉调用方到底脱没脱成，否则上游无从判断。
        "valid": result != value,
    }


def mask_id_card_api(payload: dict[str, Any]) -> dict[str, Any]:
    value = _as_text(payload, "value")
    keep_head = _as_int(payload, "keep_head", 6, minimum=0, maximum=18)
    keep_tail = _as_int(payload, "keep_tail", 4, minimum=0, maximum=18)
    result = mask_id_card(value, keep_head, keep_tail)
    return {
        "value": value,
        "result": result,
        "masked": result != value,
        "valid": result != value,
    }


def mask_scan(payload: dict[str, Any]) -> dict[str, Any]:
    """扫描正文，把里面的手机号和身份证号全部打码。

    顺序很关键：**先脱身份证，再脱手机号**。
    18 位身份证号里天然包含 11 位连续数字，如果先跑手机号规则，
    身份证会被从中间拦腰截断，脱完变成一个既不像身份证也不像手机号的残串。
    """
    text = _as_text(payload, "text")

    # 第一步必须先处理身份证：18 位身份证里天然含 11 位连续数字，
    # 会命中手机号正则（如 110101199003071234 里的 19900307123）
    id_count = len(_ID_SCAN_RE.findall(text))
    stage1 = _ID_SCAN_RE.sub(lambda m: mask_id_card(m.group(0)), text)

    # 手机号必须在「身份证已打码」的文本上统计。
    # 这一步很容易漏：只在做替换时保证顺序、统计却在原文上做，
    # 结果就是命中数虚高一倍，而替换结果明明是对的——数据对不上还查不出原因。
    phone_count = len(_PHONE_SCAN_RE.findall(stage1))
    result = _PHONE_SCAN_RE.sub(lambda m: mask_phone(m.group(0)), stage1)

    return {
        "text": text,
        "result": result,
        "id_card_count": id_count,
        "phone_count": phone_count,
        "total": id_count + phone_count,
    }


def money_rmb(payload: dict[str, Any]) -> dict[str, Any]:
    amount = _as_amount(payload)
    result = _call(to_rmb_upper, amount, field="amount")
    return {
        "amount": str(amount),
        "result": result,
    }


# ---------------------------------------------------------------------------
# 批量处理
# ---------------------------------------------------------------------------
def _single(kind: str, raw: str, options: dict[str, Any]) -> str:
    """对单行执行指定转换，返回结果字符串。"""
    if kind == "phone":
        return mask_phone(raw, options.get("keep_head", 3), options.get("keep_tail", 4))
    if kind == "id-card":
        return mask_id_card(raw, options.get("keep_head", 6), options.get("keep_tail", 4))
    if kind == "rmb":
        return str(_call(to_rmb_upper, raw, field=f"line:{raw[:20]}"))
    if kind == "slug":
        return to_slug(raw, options.get("max_length", 60))
    if kind == "count":
        return str(count_words(raw))
    if kind == "width":
        return str(display_width(raw))
    if kind == "truncate":
        return truncate_by_width(raw, options.get("width", 20), options.get("suffix", "…"))
    if kind == "scan":
        return str(mask_scan({"text": raw})["result"])
    raise BadRequest(f"未知的批量函数：{kind}")


BATCH_FUNCTIONS = (
    "phone",
    "id-card",
    "rmb",
    "slug",
    "count",
    "width",
    "truncate",
    "scan",
)


def batch(payload: dict[str, Any]) -> dict[str, Any]:
    """逐行转换。

    单行失败不会中断整批——这跟 pystrkit 里脱敏函数「不抛异常」是同一个取舍：
    处理 5000 行日志时，不应该因为第 37 行是个脏数据就让前 36 行白干。
    但金额转换失败必须被看见，所以失败行会带上 error 字段，前端标红。
    """
    text = _as_text(payload, "text")
    kind = str(_require(payload, "fn"))
    if kind not in BATCH_FUNCTIONS:
        raise BadRequest(f"未知的批量函数：{kind}，可选值：{', '.join(BATCH_FUNCTIONS)}")

    options = payload.get("options") or {}
    if not isinstance(options, dict):
        raise BadRequest("参数 options 必须是对象")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) > _MAX_BATCH_LINES:
        raise BadRequest(f"行数超过上限 {_MAX_BATCH_LINES}")

    items: list[dict[str, Any]] = []
    failed = 0
    for index, raw in enumerate(lines, start=1):
        row: dict[str, Any] = {"index": index, "input": raw}
        try:
            row["output"] = _single(kind, raw, options)
            row["ok"] = True
        except (ValueError, InvalidArgument, BadRequest) as exc:
            # 只捕获「数据问题」，不吞掉程序 bug——那是 500 该管的事
            row["output"] = ""
            row["ok"] = False
            row["error"] = str(exc)
            failed += 1
        items.append(row)

    return {
        "fn": kind,
        "total": len(items),
        "failed": failed,
        "items": items,
    }


# ---------------------------------------------------------------------------
# 注册表：HTTP 层只认这张表
# ---------------------------------------------------------------------------
Handler = Callable[[dict[str, Any]], dict[str, Any]]

ENDPOINTS: dict[str, Handler] = {
    "text.width": text_width,
    "text.count": text_count,
    "text.truncate": text_truncate,
    "text.slug": text_slug,
    "mask.phone": mask_phone_api,
    "mask.id-card": mask_id_card_api,
    "mask.scan": mask_scan,
    "money.rmb": money_rmb,
    "batch": batch,
}


def invoke(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """按名字调用一个接口。payload 不是 dict 时直接拒绝。"""
    handler = ENDPOINTS.get(name)
    if handler is None:
        raise BadRequest(f"未知接口：{name}")
    if not isinstance(payload, dict):
        raise BadRequest("请求体必须是 JSON 对象")
    return handler(payload)
