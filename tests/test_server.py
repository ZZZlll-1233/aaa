"""HTTP 层测试：起真实服务，用标准库 http.client 打过去。

为什么不用 mock？因为这层最容易出的就是「Content-Length 算错」
「状态码映射错」「静态文件 404」这类只有真跑才会暴露的问题。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from typing import Any

import pytest

from pystrkit_web.server import make_server


@pytest.fixture()
def server() -> Iterator[str]:
    """在随机端口起服务，测试结束关掉。"""
    httpd = make_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def request(
    base: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, bytes]:
    host, port = base.split(":")
    conn = HTTPConnection(host, int(port), timeout=5)
    try:
        headers: dict[str, str] = {}
        payload: bytes | None = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, payload, headers)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, raw
    finally:
        conn.close()


def get_json(base: str, path: str) -> tuple[int, dict[str, Any]]:
    status, raw = request(base, "GET", path)
    body: dict[str, Any] = json.loads(raw.decode("utf-8"))
    return status, body


def post_json(base: str, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    status, raw = request(base, "POST", path, body)
    parsed: dict[str, Any] = json.loads(raw.decode("utf-8"))
    return status, parsed


def test_health(server: str) -> None:
    status, data = get_json(server, "/api/health")
    assert status == 200
    assert data["ok"] is True
    assert data["data"]["status"] == "ok"


def test_index_page(server: str) -> None:
    status, raw = request(server, "GET", "/")
    assert status == 200
    assert "pystrkit" in raw.decode("utf-8")


def test_static_css(server: str) -> None:
    conn_host, port = server.split(":")
    from http.client import HTTPConnection

    conn = HTTPConnection(conn_host, int(port), timeout=5)
    try:
        conn.request("GET", "/static/style.css")
        resp = conn.getresponse()
        resp.read()  # 读完再关，否则服务端会记一条连接中断
        assert resp.status == 200
        assert "text/css" in resp.headers.get("Content-Type", "")
    finally:
        conn.close()


def test_post_endpoint(server: str) -> None:
    status, data = post_json(server, "/api/money/rmb", {"amount": "1234.56"})
    assert status == 200
    assert data["data"]["result"] == "壹仟贰佰叁拾肆元伍角陆分"


def test_route_with_dash(server: str) -> None:
    """验证 /api/mask/id-card 能正确映射成 mask.id-card。"""
    status, data = post_json(server, "/api/mask/id-card", {"value": "110101199003071234"})
    assert status == 200
    assert data["data"]["result"] == "110101********1234"


def test_error_status_mapping(server: str) -> None:
    """金额解析失败应该是 400，不能是 500。"""
    status, data = post_json(server, "/api/money/rmb", {"amount": "abc"})
    assert status == 400
    assert data["ok"] is False
    assert data["error"]["code"] == "invalid_argument"


def test_bad_json(server: str) -> None:
    host, port = server.split(":")
    from http.client import HTTPConnection

    conn = HTTPConnection(host, int(port), timeout=5)
    try:
        conn.request("POST", "/api/text/width", b"{not json", {"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 400
        assert body["error"]["code"] == "bad_request"
    finally:
        conn.close()


def test_404(server: str) -> None:
    status, data = post_json(server, "/api/does/not/exist", {})
    assert status == 404


def test_get_on_post_only_endpoint(server: str) -> None:
    status, _ = get_json(server, "/api/money/rmb")
    assert status == 405


def test_directory_traversal_blocked(server: str) -> None:
    status, _ = request(server, "GET", "/static/../server.py")
    assert status in (404, 400)


def test_openapi(server: str) -> None:
    status, doc = get_json(server, "/api/openapi.json")
    assert status == 200
    assert doc["openapi"].startswith("3.")
    assert "/api/money/rmb" in doc["paths"]


def test_functions_list(server: str) -> None:
    status, data = get_json(server, "/api/functions")
    assert status == 200
    names = [i["name"] for i in data["data"]["items"]]
    assert "money.rmb" in names
    assert "mask.id-card" in names


def test_batch_endpoint(server: str) -> None:
    status, data = post_json(server, "/api/batch", {"fn": "phone", "text": "13812345678\n12345"})
    assert status == 200
    assert data["data"]["total"] == 2
    assert data["data"]["items"][0]["output"] == "138****5678"
