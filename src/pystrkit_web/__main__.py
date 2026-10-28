"""命令行入口：``python -m pystrkit_web``。"""

from __future__ import annotations

import argparse
import importlib.util
import sys


def _check_dependency() -> None:
    """pystrkit 是硬依赖，缺失时给一条能照做的修复命令，别只抛 ImportError。"""
    if importlib.util.find_spec("pystrkit") is not None:
        return
    print(
        "错误：找不到 pystrkit。\n"
        "\n"
        "pystrkit-web 只是界面层，文本处理能力在 pystrkit 里。请先安装：\n"
        "\n"
        "    pip install pystrkit            # 从 PyPI\n"
        "    pip install -e ../pystrkit      # 或者从本地源码目录\n"
        "\n"
        "如果已经装了但仍报这个错，检查是否装到了另一个 Python 环境：\n"
        f"    {sys.executable} -m pip install -e ../pystrkit\n",
        file=sys.stderr,
    )
    raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pystrkit-web",
        description="启动 pystrkit 的 Web 界面（含 REST API）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python -m pystrkit_web                # 默认 http://127.0.0.1:8765\n"
            "  python -m pystrkit_web --port 9000    # 换端口\n"
            "  python -m pystrkit_web --host 0.0.0.0 # 允许局域网访问\n"
        ),
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--quiet", action="store_true", help="不打印访问日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _check_dependency()

    from .server import run

    run(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        quiet=args.quiet,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
