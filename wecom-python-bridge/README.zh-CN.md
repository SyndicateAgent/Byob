# BYOB 企业微信 Python Bridge

这个目录是 OpenClaw 旁路的 Python 替代方案。它不启动 OpenClaw gateway，也不 patch OpenClaw 插件，而是用企业微信智能机器人长连接 SDK 直接连接企业微信，再把文本消息转给 BYOB QA Agent。

链路：

```text
企业微信长连接网关
        ↑ WebSocket 出站连接
Python bridge
        ↓ HTTP
BYOB /api/v1/agent/ask
```

长连接模式下，本机不需要公网 webhook。Python bridge 是 WebSocket client，主动连接企业微信。

## 状态

当前实现已经在本机完成以下验证：

- `wecom-aibot-sdk==1.0.6` 可以安装并导入。
- `WSClient.on()`、`connect()`、`reply_stream()`、`send_message()` 方法存在。
- Python bridge 可以用企业微信 Bot ID/Secret 建立长连接并认证成功。
- Python bridge 的 BYOB client 可以调用本机 `/api/v1/agent/ask`，并返回 MiniMax-M2.7 生成答案。

完整业务验证仍需要从企业微信给机器人发送一条真实文本消息。

## 前置条件

先启动 BYOB：

- API：`http://127.0.0.1:8000`
- MCP：`http://127.0.0.1:8010/mcp`
- Worker：如果需要新增文档，启动 ingestion worker
- 可选 LLM：如果 `BYOB_AGENT_USE_LLM=true`，先配置 BYOB 的 `AGENT_LLM_*`

企业微信机器人必须由人类管理员在企业微信管理后台创建：

1. 登录企业微信管理后台。
2. 进入 `安全与管理` -> `管理工具` -> `智能机器人`。
3. 创建机器人，选择 `API 模式创建`。
4. 连接方式选择 `使用长连接`。
5. 保存并复制 `Bot ID` 和 `Secret`。

官方文档：
`https://open.work.weixin.qq.com/help2/pc/cat?doc_id=21657`

## 安装

从 BYOB 仓库根目录执行：

```powershell
cd .\wecom-python-bridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .\env.example .\env.local
```

如果 Windows `py -3.12` 启动器找不到 Python，可以用 BYOB 已有 venv 的 Python 创建独立 venv：

```powershell
F:\AI\Codex\BYOB\.venv\Scripts\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

编辑 `env.local`：

```text
WECOM_BOT_ID=<企业微信 Bot ID>
WECOM_SECRET=<企业微信 Secret>

BYOB_API_BASE_URL=http://127.0.0.1:8000
BYOB_API_EMAIL=admin@example.com
BYOB_API_PASSWORD=<本地 BYOB 密码>
BYOB_AGENT_USE_LLM=true
```

也可以不用 BYOB 账号密码，改用固定 token：

```text
BYOB_API_TOKEN=<BYOB bearer token>
```

不要提交 `env.local`。

## 启动

确保没有 OpenClaw gateway 仍在运行。当前测试中 OpenClaw 已被停止，默认 `18789` 不再监听。

启动 Python bridge：

```powershell
.\scripts\start-bridge.ps1
```

隐藏窗口后台启动：

```powershell
.\scripts\start-bridge-hidden.ps1
```

隐藏启动后会写入：

```text
bridge.pid
logs\bridge.err.log
logs\bridge.out.log
```

看到下面日志说明企业微信长连接认证成功：

```text
WeCom long connection authenticated
```

停止后台 bridge：

```powershell
.\scripts\stop-bridge.ps1
```

或直接运行：

```powershell
.\.venv\Scripts\python.exe -m byob_wecom_bridge.main
```

## 行为

- 收到 `message.text` 后，提取文本并调用 BYOB。
- BYOB API：`POST /api/v1/agent/ask`
- `BYOB_AGENT_USE_LLM=true` 时，BYOB 会调用自己配置的 LLM。
- `BYOB_AGENT_USE_LLM=false` 时，只返回 BYOB 的 extractive answer，适合验证 RAG 检索。
- 图片、文件、语音等非文本消息会回复“当前 Python bridge 只处理文本消息。”

## 环境变量

| 变量 | 是否必需 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `WECOM_BOT_ID` | 是 | 空 | 企业微信后台生成的 Bot ID。 |
| `WECOM_SECRET` | 是 | 空 | 企业微信后台生成的 Secret。 |
| `BYOB_API_BASE_URL` | 否 | `http://127.0.0.1:8000` | BYOB API 地址。 |
| `BYOB_API_TOKEN` | 二选一 | 空 | 固定 BYOB bearer token。 |
| `BYOB_API_EMAIL` | 二选一 | 空 | BYOB 登录邮箱。 |
| `BYOB_API_PASSWORD` | 二选一 | 空 | BYOB 登录密码。 |
| `BYOB_AGENT_USE_LLM` | 否 | `true` | 传给 `/api/v1/agent/ask` 的 `use_llm`。 |
| `BYOB_AGENT_TOP_K` | 否 | `5` | 检索 `top_k`，限制在 1 到 20。 |
| `BYOB_BRIDGE_TIMEOUT_MS` | 否 | `180000` | BYOB 登录和问答请求超时。 |
| `BYOB_TEXT_MAX_CHARS` | 否 | `12000` | 发回企业微信的最大字符数。 |
| `BYOB_SEND_THINKING_MESSAGE` | 否 | `true` | 是否先发送“正在检索”流式消息。 |

## 验证

1. 启动 BYOB API/MCP。
2. 启动 Python bridge。
3. 从企业微信给机器人发一条文本消息。
4. bridge 日志应出现 `Forwarding WeCom text to BYOB`。
5. BYOB API 应收到 `/api/v1/agent/ask`。
6. 企业微信应收到 BYOB 的 Markdown 答案。

## 和 OpenClaw 方案的区别

- Python bridge 不依赖 OpenClaw，也不调用 OpenClaw 模型 provider。
- Python bridge 不需要 patch `@wecom/wecom-openclaw-plugin`。
- Python bridge 只覆盖当前 BYOB 文本问答场景；如果后续要用 OpenClaw channel/plugin 生态，应继续使用 `openclaw/` 方案。

## 注意事项

- 不要提交 `env.local` 或任何 Secret。
- 不要把企业微信 `Secret` 写入 README、命令历史或日志。
- 这个实现基于 `wecom-aibot-sdk==1.0.6`。如果 SDK API 改动，需要同步调整 `byob_wecom_bridge/wecom_adapter.py`。
