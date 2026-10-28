"""OpenAPI 3.0 文档描述。

为什么要自带一份而不是手写 Markdown？
因为前端「API 文档」页要渲染它，而且它是从代码里生成的结构化数据，
接口改了不会跟文档脱节。手写文档必然过期，这是铁律。
"""

from __future__ import annotations

from typing import Any

from .api import BATCH_FUNCTIONS, ENDPOINTS

#: 每个接口的中文说明与示例入参，前端和 /api/openapi.json 都读它
DOCS: dict[str, dict[str, Any]] = {
    "text.width": {
        "summary": "计算显示宽度",
        "description": "中文等全角字符按 2 计，ASCII 按 1 计。做终端表格对齐时用得上。",
        "example": {"text": "中文abc"},
    },
    "text.count": {
        "summary": "中英混排字数统计",
        "description": "每个汉字算 1 字，每个英文单词算 1 词，标点不计数。",
        "example": {"text": "Python 是最好的语言"},
    },
    "text.truncate": {
        "summary": "按显示宽度截断",
        "description": "超出部分用 suffix 替代，返回值的宽度保证不超过 width。",
        "example": {"text": "中文文本处理工具库", "width": 6},
    },
    "text.slug": {
        "summary": "生成 URL slug",
        "description": "中文会被移除（转拼音需要额外依赖，本库不做）。",
        "example": {"text": "Hello, Gitee! 开源 项目"},
    },
    "mask.phone": {
        "summary": "手机号脱敏",
        "description": "格式不合法时原样返回，不抛异常；用返回的 valid 字段判断是否脱成功。",
        "example": {"value": "13812345678"},
    },
    "mask.id-card": {
        "summary": "身份证号脱敏",
        "description": "18 位二代身份证，末位可为 X。同样不抛异常。",
        "example": {"value": "110101199003071234"},
    },
    "mask.scan": {
        "summary": "全文扫描脱敏",
        "description": "从一段正文里捞出所有手机号与身份证号并打码，返回命中数量。",
        "example": {"text": "用户 13812345678（身份证 110101199003071234）于今日登录"},
    },
    "money.rmb": {
        "summary": "人民币转中文大写",
        "description": "财务口径：先转 Decimal 再量化到分，ROUND_HALF_UP。传字符串最安全。",
        "example": {"amount": "1234.56"},
    },
    "batch": {
        "summary": "批量逐行转换",
        "description": "单行失败不中断整批，失败行带 error 字段。可选 fn："
        + "、".join(BATCH_FUNCTIONS),
        "example": {"fn": "phone", "text": "13812345678\n13900001111"},
    },
}


def path_for(name: str) -> str:
    """接口名 -> URL 路径。text.width -> /api/text/width。"""
    return "/api/" + name.replace(".", "/")


def build() -> dict[str, Any]:
    """生成 OpenAPI 3.0 文档。"""
    paths: dict[str, Any] = {}
    for name in ENDPOINTS:
        doc = DOCS.get(name, {})
        paths[path_for(name)] = {
            "post": {
                "summary": doc.get("summary", name),
                "description": doc.get("description", ""),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"},
                            "example": doc.get("example", {}),
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "成功，data 字段为结果对象",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean", "example": True},
                                        "data": {"type": "object"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "入参错误或值不合法"},
                },
            }
        }

    paths["/api/health"] = {
        "get": {"summary": "健康检查", "responses": {"200": {"description": "服务正常"}}}
    }
    paths["/api/functions"] = {
        "get": {
            "summary": "列出所有可用接口",
            "responses": {"200": {"description": "接口清单"}},
        }
    }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "pystrkit-web",
            "version": "0.1.0",
            "description": "pystrkit 的 Web 接口层：中文文本处理、脱敏、人民币大写。",
            "license": {"name": "Apache-2.0"},
        },
        "servers": [{"url": "http://127.0.0.1:8765", "description": "本地"}],
        "paths": paths,
    }


def function_list() -> list[dict[str, Any]]:
    """给前端用的简化清单。"""
    items = []
    for name in ENDPOINTS:
        doc = DOCS.get(name, {})
        items.append(
            {
                "name": name,
                "path": path_for(name),
                "method": "POST",
                "summary": doc.get("summary", name),
                "description": doc.get("description", ""),
                "example": doc.get("example", {}),
            }
        )
    return items
