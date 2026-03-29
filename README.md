# Grok 批量注册工具

批量注册 Grok 账号，自动完成邮箱验证、Turnstile 人机验证、TOS 同意及 NSFW 功能开启。

## 功能特性

- 自动生成临时邮箱（基于 freemail 服务）
- 自动接收并提取邮箱验证码（`XXX-XXX` 格式，去横杠提交）
- 本地 Turnstile 验证码自动解决（camoufox 浏览器自动化）
- 自动完成注册 → SSO 获取 → TOS 同意 → NSFW 启用全流程
- NSFW 启用采用浏览器自动化绕过 Cloudflare Managed Challenge
- 支持 HTTP 代理（Clash 等）
- 多线程并发注册
- 注册完成后自动清理临时邮箱
- SSO Token 自动保存到文件

## 项目结构

```
grokzhuce/
├── grok.py                    # 主程序，批量注册入口
├── api_solver.py              # Turnstile 验证码解决器（本地 HTTP 服务）
├── open_grok.py               # 用 SSO 打开浏览器登录 grok.com
├── TurnstileSolver.bat        # Turnstile Solver Windows 启动脚本
├── .env                       # 环境变量配置
├── .env.example               # 环境变量模板
├── requirements.txt           # Python 依赖
├── g/                         # 核心服务模块
│   ├── __init__.py            # 包导出
│   ├── email_service.py       # freemail 临时邮箱 API 客户端
│   ├── turnstile_service.py   # Turnstile 验证服务（本地/YesCaptcha）
│   ├── user_agreement_service.py  # TOS 同意（gRPC-web）
│   ├── nsfw_service.py        # NSFW 设置（gRPC-web，直连方式）
│   ├── cf_nsfw_browser.py     # NSFW 浏览器方式（子进程调用入口）
│   ├── nsfw_browser_worker.py # NSFW 浏览器自动化子进程（camoufox）
│   ├── browser_configs.py     # 浏览器指纹配置
│   └── db_results.py          # 验证结果内存存储
└── keys/                      # 注册成功的 SSO Token 输出目录
    └── grok_YYYYMMDD_HHMMSS_N.txt
```

## 前置依赖

| 依赖项 | 说明 |
|--------|------|
| Python 3.10+ | 运行环境 |
| Node.js 18+ | 部署 freemail 所需 |
| [freemail](https://github.com/nicemove/freemail) | Cloudflare Workers 临时邮箱服务（需自行部署） |
| Clash 等代理工具 | 可选，用于科学上网访问 grok.com |

## 安装步骤

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
pip install quart rich aiosqlite patchright camoufox
```

> `requirements.txt` 包含基础依赖：`curl_cffi`、`beautifulsoup4`、`python-dotenv`、`requests`
>
> Turnstile Solver 额外需要：`quart`、`rich`、`aiosqlite`、`patchright`、`camoufox`

### 2. 安装浏览器内核

```bash
python -m patchright install chromium
python -m camoufox fetch
```

### 3. 部署 freemail 临时邮箱服务

freemail 是基于 Cloudflare Workers + D1 + R2 + Email Routing 的临时邮箱服务：

1. 克隆 [freemail 项目](https://github.com/nicemove/freemail)
2. 配置 `wrangler.toml`（设置域名、JWT Token 等）
3. 创建 D1 数据库和 R2 存储桶
4. 使用 `npx wrangler deploy` 部署
5. 在 Cloudflare 配置 Email Routing，将域名邮件转发到 Worker

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# freemail API 配置
WORKER_DOMAIN=your-freemail-worker.your-subdomain.workers.dev
FREEMAIL_TOKEN=your-jwt-token

# Turnstile 验证配置
# 留空则使用本地 Solver（推荐）
YESCAPTCHA_KEY=
```

### 5. 配置代理（可选但推荐）

如果需要通过代理访问 grok.com，编辑 `grok.py` 中的 `PROXIES` 字典：

```python
PROXIES = {
    "http": "http://127.0.0.1:7897",   # Clash 默认端口 7890，Clash Verge 默认 7897
    "https": "http://127.0.0.1:7897"
}
```

同时需要修改 `g/nsfw_service.py`、`g/user_agreement_service.py` 和 `g/nsfw_browser_worker.py` 中的代理地址保持一致。

## 快速启动

> **前提条件**：Clash 代理已开启（端口 7897）、freemail 邮箱服务已部署。

整个系统需要 **2 个终端**配合运行：

### 终端 1：启动 Turnstile Solver

```powershell
cd f:\grok注册\grokzhuce-main\grokzhuce-main
$env:PYTHONIOENCODING="utf-8"
python api_solver.py --browser_type camoufox --thread 2 --debug
```

等待出现 `Running on http://0.0.0.0:5072` 表示就绪，**不要关闭此终端**。

### 终端 2：运行注册程序

```powershell
cd f:\grok注册\grokzhuce-main\grokzhuce-main
$env:PYTHONUNBUFFERED="1"
python -u grok.py 2 5
```

其中 `2` 是并发线程数，`5` 是要注册的账号数量，根据需要调整。

也可以不带参数以交互方式运行：

```powershell
python grok.py
# 按提示输入并发数和注册数量
```

### 注册完成后

SSO Token 自动保存在 `keys/` 目录下，用以下命令打开浏览器直接登录：

```powershell
python open_grok.py keys/grok_20260318_145646_1.txt
```

### Turnstile Solver 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--browser_type` | 浏览器类型（`camoufox`/`chromium`/`chrome`） | `chromium` |
| `--thread` | 浏览器并发数（越大越耗 CPU） | `4` |
| `--debug` | 启用调试日志 | 关闭 |
| `--no-headless` | 显示浏览器窗口（调试用） | 无头模式 |
| `--port` | 监听端口 | `5072` |

## 注册流程

```
生成临时邮箱 → 发送验证码 → 轮询获取验证码 → 验证验证码
    → Turnstile 人机验证 → 提交注册 → 获取 SSO Token
    → 接受 TOS → 启用 NSFW（直连 → 浏览器自动化）
    → 保存 SSO Token → 清理临时邮箱
```

每个账号的注册流程约 **40-70 秒**（含 NSFW 浏览器验证）。

## 使用 SSO Token

注册成功的 SSO Token 保存在 `keys/` 目录下。

### 浏览器手动登录

1. 打开浏览器访问 `https://grok.com`
2. 按 `F12` → `Application` → `Cookies` → `https://grok.com`
3. 添加 Cookie：`Name=sso`，`Value=你的SSO Token`，`Domain=.grok.com`
4. 刷新页面即可登录

### 脚本自动登录

```bash
python open_grok.py keys/grok_YYYYMMDD_HHMMSS_N.txt
```

自动打开浏览器并注入 SSO Cookie 访问 grok.com。

### API 调用

```python
import requests
cookies = {"sso": "eyJ0eXAiOiJKV1QiLCJhbGci..."}
resp = requests.get("https://grok.com/api/...", cookies=cookies)
```

## 输出示例

```
============================================================
Grok 注册机
============================================================
[*] 正在初始化...
[+] Action ID: 7f69646bb11542f4cad728680077c67a09624b94e0
[*] 启动 2 个线程，目标 2 个
[*] 输出: keys/grok_20260318_145646_2.txt
[*] 开始注册: w9wffsvr@juedingbaolongwang.online
[*] w9wffsvr@juedingbaolongwang.online 验证码: 7A5C22
[*] w9wffsvr@juedingbaolongwang.online Turnstile OK, 提交注册...
[*] w9wffsvr@juedingbaolongwang.online 获取SSO成功, 接受TOS...
[*] w9wffsvr@juedingbaolongwang.online 启用NSFW...
[!] w9wffsvr@juedingbaolongwang.online NSFW直连失败(403 Forbidden), 尝试浏览器方式...
[+] w9wffsvr@juedingbaolongwang.online NSFW浏览器方式启用成功!
[+] 1/2 w9wffsvr@juedingbaolongwang.online | 68.2s/个

[*] 开始二次验证 NSFW（浏览器方式）...
[+] NSFW启用成功: eyJ0eXAiOiJKV1QiLCJh...
[*] 二次验证完成: 1/1
```

## 技术细节

### NSFW 启用机制

grok.com 启用了 Cloudflare Managed Challenge 保护，直接 HTTP 请求会被 403 拦截。解决方案：

1. **直连尝试**：先用 `curl_cffi`（TLS 指纹模拟）直接发送 gRPC 请求
2. **浏览器回退**：如果直连 403，自动启动 camoufox 浏览器：
   - 打开 grok.com 并带上 SSO Cookie
   - 通过 `page.frames` API 找到 Cloudflare Turnstile iframe（在 shadow DOM 中）
   - 坐标点击复选框通过验证
   - 获取 `cf_clearance` Cookie 后在浏览器内发送 gRPC 请求

### 验证码格式

Grok 的邮箱验证码格式为 `XXX-XXX`（如 `7A5-C22`），提交时需**去掉中间横杠**（如 `7A5C22`）。

### 代理配置

所有访问 `accounts.x.ai` 和 `grok.com` 的请求均走代理，涉及文件：

- `grok.py` → `PROXIES` 字典（注册主流程）
- `g/nsfw_service.py` → NSFW 直连请求
- `g/user_agreement_service.py` → TOS 同意请求
- `g/nsfw_browser_worker.py` → 浏览器代理（默认 `http://127.0.0.1:7897`）

## 常见问题

### Q: 发送验证码异常

检查代理是否启动。所有请求默认走 Clash 代理端口，如果 Clash 未运行会报 `ConnectionRefusedError`。

### Q: 验证码收不到

确认 freemail 的 Email Routing 配置正确，检查 Cloudflare 仪表盘的 Email Routing 日志。

### Q: NSFW 启用失败

NSFW 需要绕过 Cloudflare 保护，确保 camoufox 已正确安装（`python -m camoufox fetch`）。

### Q: CPU 占用过高

Turnstile Solver 的 `--thread` 参数控制浏览器实例数。降低到 2 可减少资源占用。

## 注意事项

- 需要自行部署 freemail 临时邮箱服务并配置域名 Email Routing
- 运行前必须先启动 Turnstile Solver
- 代理端口需与实际 Clash 端口一致
- 仅供学习研究使用
