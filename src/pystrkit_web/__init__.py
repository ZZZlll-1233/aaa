"""pystrkit-web —— 给 pystrkit 加一层 Web 服务与浏览器界面。

设计约束与 pystrkit 保持一致：**零第三方依赖**。
后端只用标准库 http.server，前端只用原生 HTML/CSS/JS，不引任何框架和 CDN。
这样它可以直接扔进内网机器离线运行，也方便读代码——总共就 5 个 Python 模块。

模块分工：

- ``api``      纯业务逻辑，输入 dict 输出 dict，不碰 HTTP，可直接单测
- ``server``   HTTP 层：路由、静态文件、错误处理、访问日志
- ``openapi``  OpenAPI 3.0 描述，前端「API 文档」页直接读它渲染
- ``__main__`` 命令行入口
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
