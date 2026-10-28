"""HTTP 层：路由、静态文件、错误处理、访问日志。

只依赖标准库。用 ``ThreadingHTTPServer`` 而不是 ``HTTPServer``，
是因为浏览器会并发请求静态资源，单线程会把页面加载卡成串行。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .api import BATCH_FUNCTIONS, ENDPOINTS
from .errors import ApiError, MethodNotAllowed, NotFound, PayloadTooLarge
from .openapi import build, function_list

STATIC_DIR = Path(__file__).parent / "static"

#: 请求体上限 1 MB。这是个文本工具，超过这个量级说明调用方用错了场景
MAX_BODY = 1024 * 1024

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".woff2": "font/woff2",
}

logger = logging.getLogger("pystrkit_web")

# 页面缓存：静态文件在程序运行期间不会变，避免每次请求都读盘
_CACHE: dict[str, bytes] = {}


def _route_to_endpoint(path: str) -> str:
    """/api/mask/id-card -> mask.id-card；/api/batch -> batch。"""
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2 or parts[0] != "api":
        raise NotFound(f"接口不存在：{path}")
    rest = parts[1:]
    if len(rest) == 1:
        return rest[0]
    return rest[0] + "." + ".".join(rest[1:])


class ApiHandler(BaseHTTPRequestHandler):
    """请求处理器。所有响应统一走 `_send`，包括错误。"""

    server_version = "pystrkit-web/0.1.0"
    protocol_version = "HTTP/1.1"

    # --- 基础设施 ---------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D102
        """屏蔽 BaseHTTPRequestHandler 默认的 stderr 输出，改用自定义访问日志。"""

    def handle_one_request(self) -> None:
        """客户端提前断开时静默收尾。

        HTTP/1.1 keep-alive 下这很常见：浏览器预连接后不用、探测脚本只取
        响应头就走人。默认的 socketserver 会把它当成未捕获异常打一屏 traceback，
        把访问日志冲得没法看——那是噪音，不是故障。
        """
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            self.close_connection = True

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str = "application/json; charset=utf-8",
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # 本地工具，允许任意来源方便调试；也允许前端直接 fetch
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body)

    def _send_error(self, exc: ApiError) -> None:
        self._send_json(
            exc.status,
            {"ok": False, "error": exc.to_dict()},
        )

    def _read_body(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length")
        if not raw_len:
            raise ApiError("bad_request", "请求体为空", 400)
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise ApiError("bad_request", "Content-Length 非法", 400) from exc

        if length > MAX_BODY:
            raise PayloadTooLarge(MAX_BODY)
        if length <= 0:
            raise ApiError("bad_request", "请求体为空", 400)

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError("bad_request", "请求体不是合法 JSON", 400) from exc
        if not isinstance(payload, dict):
            raise ApiError("bad_request", "请求体必须是 JSON 对象", 400)
        return payload

    def _serve_static(self, rel_path: str) -> None:
        """静态文件服务，含目录穿越防护。"""
        if not rel_path or rel_path.endswith("/"):
            rel_path = (rel_path or "") + "index.html"

        target = (STATIC_DIR / rel_path).resolve()
        root = STATIC_DIR.resolve()
        # 关键：resolve 之后必须仍在 static 根内，否则 ../../etc/passwd 就进来了
        if not str(target).startswith(str(root)) or not target.is_file():
            raise NotFound(f"资源不存在：{rel_path}")

        suffix = target.suffix.lower()
        content_type = MIME_TYPES.get(suffix, "application/octet-stream")

        key = str(target)
        cached = _CACHE.get(key)
        if cached is None:
            cached = target.read_bytes()
            _CACHE[key] = cached
        self._send(HTTPStatus.OK, cached, content_type)

    # --- 路由 -------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"")

    def do_GET(self) -> None:  # noqa: N802
        started = time.perf_counter()
        status = 200
        try:
            path = self.path.split("?", 1)[0]
            if path.rstrip("/") == "" or path.rstrip("/") == "/index.html":
                self._serve_static("index.html")
            elif path == "/api/health":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "data": {
                            "status": "ok",
                            "endpoints": len(ENDPOINTS),
                            "batch_functions": list(BATCH_FUNCTIONS),
                        },
                    },
                )
            elif path == "/api/functions":
                self._send_json(200, {"ok": True, "data": {"items": function_list()}})
            elif path == "/api/openapi.json":
                self._send_json(200, build())
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/") :])
            elif path.startswith("/api/"):
                raise MethodNotAllowed("该接口只支持 POST")
            else:
                # 未知路径一律当作静态资源，找不到就 404
                self._serve_static(path.lstrip("/"))
        except ApiError as exc:
            status = exc.status
            self._send_error(exc)
        except Exception:  # noqa: BLE001
            status = 500
            self._handle_unexpected()
        finally:
            self._log_access(started, status)

    def do_POST(self) -> None:  # noqa: N802
        started = time.perf_counter()
        status = 200
        try:
            path = self.path.split("?", 1)[0]
            if not path.startswith("/api/"):
                raise NotFound(f"接口不存在：{path}")

            name = _route_to_endpoint(path)
            if name not in ENDPOINTS:
                raise NotFound(f"接口不存在：{name}")

            payload = self._read_body()
            from .api import invoke  # 局部导入避免循环依赖

            data = invoke(name, payload)
            status = 200
            self._send_json(200, {"ok": True, "data": data})
        except ApiError as exc:
            status = exc.status
            self._send_error(exc)
        except Exception:  # noqa: BLE001
            status = 500
            self._handle_unexpected()
        finally:
            self._log_access(started, status)

    def _handle_unexpected(self) -> None:
        """未预期错误：记完整堆栈到日志，只把 trace id 回给客户端。

        不能把 traceback 直接返回——那是给攻击者的地图。
        """
        trace_id = uuid.uuid4().hex[:12]
        logger.exception("未预期错误 trace_id=%s", trace_id)
        self._send_json(
            500,
            {
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": f"服务内部错误，请查看服务端日志（trace_id={trace_id}）",
                },
            },
        )

    def _log_access(self, started: float, status: int) -> None:
        cost_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s %s -> %d (%.1f ms)",
            self.command,
            self.path,
            status,
            cost_ms,
        )


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """创建服务器实例（不阻塞），便于测试里起真实服务。"""
    return ThreadingHTTPServer((host, port), ApiHandler)


def run(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    quiet: bool = False,
) -> None:
    """启动服务并阻塞直到 Ctrl+C。"""
    logging.basicConfig(
        level=logging.WARNING if quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    server = make_server(host, port)
    url = f"http://{host}:{port}/"
    print(f"pystrkit-web 已启动：{url}")
    print("按 Ctrl+C 停止")

    if open_browser:
        import webbrowser

        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭…")
    finally:
        server.server_close()
