# pystrkit-web

给 [pystrkit](https://gitee.com/YOUR_USER/pystrkit) 加一层 Web 界面和 REST API。

后端 Python 标准库 `http.server`，前端原生 HTML/CSS/JS——**零第三方依赖**，
不引 Flask/FastAPI、不引任何前端框架、不连 CDN。整个项目只有 5 个 Python 模块加 3 个前端文件。

## 快速开始

```bash
# 1. 安装（pystrkit 是唯一依赖）
pip install -e .
pip install pystrkit            # 如果还没装

# 2. 启动
python -m pystrkit_web
# 或指定端口
python -m pystrkit_web --port 9000 --no-browser
```

浏览器会自动打开 <http://127.0.0.1:8765/>。

验证服务活着：

```bash
curl -s http://127.0.0.1:8765/api/health
# {"ok": true, "data": {"status": "ok", "endpoints": 9, ...}}

curl -s -X POST http://127.0.0.1:8765/api/money/rmb \
  -H 'Content-Type: application/json' -d '{"amount":"1234.56"}'
# {"ok": true, "data": {"amount": "1234.56", "result": "壹仟贰佰叁拾肆元伍角陆分"}}
```

> Windows 下用 Git Bash 传中文 JSON 会被终端转成 GBK，服务端解不出来。
> 调试中文请用 Postman、curl.exe 或 Python 客户端。

## 界面

| 页签 | 做什么 |
|---|---|
| 文本处理 | 按显示宽度截断、中英混排字数、显示宽度、生成 slug |
| 脱敏 | 手机号、身份证、全文扫描脱敏（可改保留位数） |
| 金额大写 | 人民币转中文大写，非法输入实时报错 |
| 批量处理 | 粘贴多行逐行转换，结果可复制 / 导出 CSV |
| API 文档 | 由服务端实时生成的接口清单，含可直接跑的 curl |

## 目录结构

```
pystrkit-web/
├── src/pystrkit_web/
│   ├── __init__.py      包说明
│   ├── errors.py        错误类型 → HTTP 状态码映射
│   ├── api.py           业务逻辑（纯函数，dict 进 dict 出）
│   ├── server.py        HTTP 层：路由、静态文件、日志
│   ├── openapi.py       OpenAPI 3.0 文档生成
│   ├── __main__.py      命令行入口
│   └── static/
│       ├── index.html   页面结构（工具卡靠 data 属性驱动）
│       ├── app.js       前端逻辑（约 300 行，无框架）
│       └── style.css
└── tests/
    ├── test_api.py      业务层单测（不起服务）
    └── test_server.py   HTTP 层测试（起真实服务）
```

## 接口

统一 `POST` + JSON，响应 `{"ok":true,"data":{...}}`；出错 `{"ok":false,"error":{"code","message"}}`。

| 路径 | 说明 |
|---|---|
| `GET /api/health` | 健康检查 |
| `GET /api/functions` | 接口清单（前端文档页读它） |
| `GET /api/openapi.json` | OpenAPI 3.0 文档 |
| `POST /api/text/width` | 显示宽度 |
| `POST /api/text/count` | 中英混排字数 |
| `POST /api/text/truncate` | 按显示宽度截断 |
| `POST /api/text/slug` | 生成 slug |
| `POST /api/mask/phone` | 手机号脱敏 |
| `POST /api/mask/id-card` | 身份证脱敏 |
| `POST /api/mask/scan` | 全文扫描脱敏 |
| `POST /api/money/rmb` | 人民币大写 |
| `POST /api/batch` | 批量逐行转换 |

## 三个设计决定

**1. 业务层不碰 HTTP。**
`api.py` 里全是 `dict → dict` 的函数，`server.py` 只做路由和序列化。
好处是测试不用起服务，加一个接口改 `ENDPOINTS` 字典就行。

**2. 错误分两类：客户端的和服务的。**
pystrkit 抛的 `ValueError`（金额解析失败）映射成 **400**，不是 500。
调用方要能分清「我传错了」和「服务炸了」。未预期错误只回 `trace_id`，
traceback 写进服务端日志——返回给客户端等于给攻击者地图。

**3. 扫描必须先脱身份证，再脱手机号。**
18 位身份证号里天然含 11 位连续数字（`110101199003071234` 里的 `19900307123`），
会命中手机号正则。而且**计数也必须在脱敏后的文本上做**，
否则命中数虚高一倍——替换结果明明是对的，数字却对不上，很难查。

## 安全提醒

**这是无鉴权的本地工具。** 默认只监听 `127.0.0.1`。
用 `--host 0.0.0.0` 暴露到局域网或公网，等于把接口开放给所有人，
不要在有不可信网络的机器上这么做。

## 开发

```bash
pip install -e ".[dev]"
pytest                    # 33 项
ruff check . && ruff format --check src tests
mypy                      # strict
```

## License

Apache-2.0
