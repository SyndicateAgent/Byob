# BYOB OpenClaw 旁路

这个目录提供一套轻量的 OpenClaw 旁路配置，用来把企业微信智能机器人消息接到 BYOB QA Agent。

这里不会提交运行态、日志、npm 依赖或真实密钥。同事从 0 复现时，按本文步骤安装依赖、生成本地配置、应用 WeCom 插件 patch 即可。

英文版见：[README.md](./README.md)。

## 这个旁路做什么

消息链路是：

1. 企业微信用户向智能机器人发送文本消息。
2. OpenClaw 通过 WeCom WebSocket 插件收到消息。
3. BYOB bridge 在 OpenClaw 调用模型 provider 前拦截文本。
4. bridge 使用 `BYOB_API_TOKEN`，或用 `BYOB_API_EMAIL` / `BYOB_API_PASSWORD` 登录 BYOB。
5. bridge 调用 `POST /api/v1/agent/ask`。
6. BYOB 负责 MCP 检索，并按 `BYOB_AGENT_USE_LLM` 决定是否调用 BYOB 中配置的 LLM。
7. OpenClaw 把 Markdown 答案发回企业微信。

也就是说，OpenClaw 只作为企业微信传输层；检索、知识库、上下文选择和答案生成都由 BYOB 负责。

## 文件说明

- `README.md`：英文说明。
- `README.zh-CN.md`：中文说明。
- `env.example`：环境变量模板，复制为 `env.local` 后填写本地值。
- `package.json`：OpenClaw CLI 依赖和脚本。
- `config/openclaw.json.example`：脱敏后的 OpenClaw 配置模板。
- `patches/wecom-monitor-byob-bridge.patch`：给 WeCom 插件打的 BYOB 旁路 patch。
- `scripts/write-openclaw-config.ps1`：根据 `env.local` 生成 `state/openclaw.json`。
- `scripts/apply-wecom-bridge-patch.ps1`：给已安装的 WeCom 插件应用 patch。
- `scripts/start-gateway.ps1`：启动本地 OpenClaw gateway。

不会提交的本地目录/文件：

- `node_modules/`
- `state/`
- `runtime/`
- `logs/`
- `inspect/`
- `env.local`

## 前置条件

先启动 BYOB：

- API：`http://127.0.0.1:8000`
- MCP：`http://127.0.0.1:8010/mcp`
- Worker：如果需要新增文档，启动 ingestion worker
- 可选 LLM：如果 `BYOB_AGENT_USE_LLM=true`，需要先配置 BYOB 的 `AGENT_LLM_*`

当前旁路固定使用：

- OpenClaw：`2026.5.3`
- WeCom 插件：`2026.4.29`

## 人工步骤：创建企业微信长连接机器人

这一步必须由企业微信管理员在企业微信管理后台手动完成。它会生成 `Bot ID` 和 `Secret`，不要把 `Secret` 提交到仓库，只写入本地 `env.local`。

企业微信官方文档：
`https://open.work.weixin.qq.com/help2/pc/cat?doc_id=21657`

人工操作步骤：

1. 登录企业微信管理后台。
2. 进入 `安全与管理` -> `管理工具` -> `智能机器人`。
3. 点击 `创建机器人`，选择 `手动创建`。
4. 填写机器人名称、简介、头像和可见范围。
5. 滚动到底部，选择 `API 模式创建`。
6. 连接方式选择 `使用长连接`。
7. 在 Secret/配置区域生成或查看凭证。
8. 复制并保存 `Bot ID` 和 `Secret`。
9. 保存机器人。

把这两个值写入 `env.local`：

```text
WECOM_BOT_ID=<企业微信后台生成的 Bot ID>
WECOM_SECRET=<企业微信后台生成的 Secret>
```

长连接模式下，OpenClaw 会主动向企业微信 WebSocket 网关建立出站连接。因此这个 BYOB/OpenClaw 旁路不需要公网 HTTP 回调地址，也不需要 webhook 来接收用户消息。

## 从 0 安装

从 BYOB 仓库根目录执行：

```powershell
cd .\openclaw
npm install
npm install --prefix .\state\npm @wecom/wecom-openclaw-plugin@2026.4.29
Copy-Item .\env.example .\env.local
```

编辑 `env.local`：

```text
BYOB_API_BASE_URL=http://127.0.0.1:8000
BYOB_API_EMAIL=admin@example.com
BYOB_API_PASSWORD=<本地 BYOB 密码>
BYOB_AGENT_USE_LLM=true
WECOM_BOT_ID=<企业微信 Bot ID>
WECOM_SECRET=<企业微信 Secret>
```

也可以不用账号密码，改用固定 token：

```text
BYOB_API_TOKEN=<BYOB bearer token>
```

## 生成 OpenClaw 配置

在 `openclaw/` 目录下执行：

```powershell
.\scripts\write-openclaw-config.ps1
```

脚本会读取 `env.local`，生成：

```text
openclaw\state\openclaw.json
```

WeCom 插件路径会指向：

```text
<repo>\openclaw\state\npm\node_modules\@wecom\wecom-openclaw-plugin
```

## 应用 BYOB Bridge Patch

当前实现会 patch WeCom 插件的已编译文件：

```text
state\npm\node_modules\@wecom\wecom-openclaw-plugin\dist\src\monitor.js
```

从 BYOB 仓库根目录执行：

```powershell
.\openclaw\scripts\apply-wecom-bridge-patch.ps1
```

这个脚本会：

- 检查 WeCom 插件是否已安装
- 如果还没 patch，执行 `git apply`
- 如果已 patch，直接成功退出
- 执行 `node --check` 校验 JS 语法

如果 patch 失败，通常是 WeCom 插件版本不一致。请重新安装指定版本：

```powershell
cd .\openclaw
npm install --prefix .\state\npm @wecom/wecom-openclaw-plugin@2026.4.29
```

然后重新运行 patch 脚本。

## 启动

从 BYOB 仓库根目录执行：

```powershell
.\openclaw\scripts\start-gateway.ps1
```

默认 gateway 地址：

```text
http://127.0.0.1:18789
```

脚本会加载：

- `openclaw/env.local`
- `openclaw/state/openclaw.json`

并启动：

```text
openclaw gateway run --allow-unconfigured --port 18789 --bind loopback --auth none
```

## Bridge 环境变量

| 变量 | 是否必需 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `BYOB_BRIDGE_ENABLED` | 否 | `1` | 是否启用 BYOB 旁路拦截。 |
| `BYOB_API_BASE_URL` | 否 | `http://127.0.0.1:8000` | BYOB API 地址。 |
| `BYOB_API_TOKEN` | 二选一 | 空 | 固定 BYOB bearer token。 |
| `BYOB_API_EMAIL` | 二选一 | 空 | BYOB 登录邮箱。 |
| `BYOB_API_PASSWORD` | 二选一 | 空 | BYOB 登录密码。 |
| `BYOB_AGENT_USE_LLM` | 否 | `true` | 传给 `/api/v1/agent/ask` 的 `use_llm`。 |
| `BYOB_AGENT_TOP_K` | 否 | `5` | 检索 `top_k`，限制在 1 到 20。 |
| `BYOB_BRIDGE_TIMEOUT_MS` | 否 | `180000` | BYOB 登录和问答请求超时时间。 |
| `WECOM_BOT_ID` | 是 | 空 | 企业微信后台生成的 Bot ID。 |
| `WECOM_SECRET` | 是 | 空 | 企业微信后台生成的 Secret。 |

## 验证

启动后，可以从企业微信给机器人发一条文本消息。正常情况下：

1. OpenClaw 日志出现 `[byob-bridge] forwarding WeCom message to BYOB agent`。
2. BYOB API 收到 `/api/v1/agent/ask` 请求。
3. 企业微信收到 BYOB 返回的 Markdown 答案。

如果只想验证 BYOB 检索，不调用 LLM，把 `env.local` 改为：

```text
BYOB_AGENT_USE_LLM=false
```

然后重启 OpenClaw gateway。

## 注意事项

- 不要提交 `env.local`、`state/`、日志、npm 依赖或任何 Secret。
- `BYOB_AGENT_USE_LLM=true` 调用的是 BYOB 配置的 LLM，不是 OpenClaw 的模型 provider。
- `BYOB_AGENT_USE_LLM=false` 时只返回 BYOB 的 extractive answer，适合验证 RAG 检索链路。
- 当前 patch 是针对 WeCom 插件 `2026.4.29` 的实用旁路方案。生产化时，更建议把 bridge 做成独立 OpenClaw 插件，避免直接修改已安装插件的 `dist` 文件。
