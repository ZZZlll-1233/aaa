"""统一错误类型。

为什么单独抽一层？因为「库抛的异常」和「HTTP 该回什么状态码」是两件事。
pystrkit 里的 ValueError（比如金额解析失败）在语义上就是 400 客户端错误，
但如果直接在 server 层 catch Exception 一律回 500，调用方就分不清是自己的
入参错了还是服务端炸了。这里把映射关系固定下来。
"""

from __future__ import annotations


class ApiError(Exception):
    """业务错误：会被 server 层转成对应的 HTTP 状态码与 JSON 结构。"""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class BadRequest(ApiError):
    """入参缺失或类型不对。"""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__("bad_request", message, 400, detail)


class InvalidArgument(ApiError):
    """入参格式正确但值不合法，通常是把 pystrkit 的 ValueError 转过来的。"""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__("invalid_argument", message, 400, detail)


class NotFound(ApiError):
    def __init__(self, message: str = "接口不存在") -> None:
        super().__init__("not_found", message, 404)


class MethodNotAllowed(ApiError):
    def __init__(self, message: str = "方法不被允许") -> None:
        super().__init__("method_not_allowed", message, 405)


class PayloadTooLarge(ApiError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            "payload_too_large",
            f"请求体超过 {limit // 1024} KB 限制",
            413,
        )
