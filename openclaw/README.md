# BYOB OpenClaw Sidecar

Chinese version: [README.zh-CN.md](./README.zh-CN.md).

This directory contains the lightweight OpenClaw sidecar setup used to connect
Enterprise WeChat messages to the BYOB QA Agent.

The sidecar is intentionally kept small. Runtime state, logs, installed npm
packages, and secrets are ignored by git. Recreate them locally with the steps
below.

## What This Sidecar Does

The patched WeCom channel flow is:

1. Enterprise WeChat sends a text message to the WeCom bot.
2. OpenClaw receives the message through the WeCom WebSocket plugin.
3. The BYOB bridge intercepts the text before OpenClaw routes it to a model
   provider.
4. The bridge logs in to BYOB or uses `BYOB_API_TOKEN`.
5. The bridge calls `POST /api/v1/agent/ask`.
6. BYOB performs MCP-backed retrieval and optionally calls the configured LLM.
7. OpenClaw sends the Markdown answer back to Enterprise WeChat.

This makes OpenClaw a transport layer only. BYOB owns retrieval, source
selection, and answer generation.

## Files

- `README.md`: this guide.
- `env.example`: environment variables for the bridge. Copy it to `env.local`.
- `package.json`: local OpenClaw CLI dependency.
- `config/openclaw.json.example`: redacted OpenClaw config template.
- `patches/wecom-monitor-byob-bridge.patch`: patch for the installed WeCom
  plugin.
- `scripts/start-gateway.ps1`: starts the local OpenClaw gateway with BYOB
  bridge defaults.

Ignored local paths:

- `node_modules/`
- `state/`
- `runtime/`
- `logs/`
- `inspect/`
- `env.local`

## Prerequisites

Start BYOB first:

- API: `http://127.0.0.1:8000`
- MCP: `http://127.0.0.1:8010/mcp`
- Worker: ingestion worker if you need to add documents
- Optional LLM: configure BYOB `AGENT_LLM_*` variables if `BYOB_AGENT_USE_LLM=true`

OpenClaw requires a recent Node.js runtime. The current sidecar pins OpenClaw
`2026.5.3` and WeCom plugin `2026.4.29`.

## Human Step: Create The WeCom Long-Connection Bot

This step must be completed by a human Enterprise WeChat administrator. It
creates credentials in the Enterprise WeChat admin console, and the generated
`Secret` should be copied into `env.local` only.

Reference: Enterprise WeChat's intelligent robot long-connection documentation:
`https://open.work.weixin.qq.com/help2/pc/cat?doc_id=21657`.

Human operator steps:

1. Log in to the Enterprise WeChat admin console.
2. Open `Security and Management` -> `Management Tools` -> `Intelligent Robot`.
3. Click `Create Robot`, then choose `Manual Creation`.
4. Fill in the robot name, description, avatar, and visible scope.
5. Scroll to the bottom and choose `API Mode Creation`.
6. In connection mode, choose `Use Long Connection`.
7. In the Secret/configuration area, click to generate or view the credentials.
8. Copy and store the generated `Bot ID` and `Secret`.
9. Save the robot.

For this sidecar, put those values in `env.local`:

```text
WECOM_BOT_ID=<Bot ID from Enterprise WeChat>
WECOM_SECRET=<Secret from Enterprise WeChat>
```

Long connection means OpenClaw connects outbound to Enterprise WeChat's
WebSocket gateway. The BYOB/OpenClaw sidecar does not need a public HTTP
callback URL or webhook for receiving user messages in this mode.

## Setup

From the BYOB repo root:

```powershell
cd .\openclaw
npm install
npm install --prefix .\state\npm @wecom/wecom-openclaw-plugin@2026.4.29
Copy-Item .\env.example .\env.local
```

Edit `env.local`:

```text
BYOB_API_BASE_URL=http://127.0.0.1:8000
BYOB_API_EMAIL=admin@example.com
BYOB_API_PASSWORD=<local BYOB password>
BYOB_AGENT_USE_LLM=true
WECOM_BOT_ID=<enterprise wechat bot id>
WECOM_SECRET=<enterprise wechat secret>
```

You can use `BYOB_API_TOKEN` instead of `BYOB_API_EMAIL` and
`BYOB_API_PASSWORD`.

Generate `state/openclaw.json`:

```powershell
.\scripts\write-openclaw-config.ps1
```

The plugin path should resolve to:

```text
<repo>\openclaw\state\npm\node_modules\@wecom\wecom-openclaw-plugin
```

## Apply The BYOB Bridge Patch

The bridge currently patches the installed WeCom plugin distribution file:

```text
state\npm\node_modules\@wecom\wecom-openclaw-plugin\dist\src\monitor.js
```

Apply the patch from the BYOB repo root:

```powershell
.\openclaw\scripts\apply-wecom-bridge-patch.ps1
```

Validate the patched JavaScript:

```powershell
node --check .\openclaw\state\npm\node_modules\@wecom\wecom-openclaw-plugin\dist\src\monitor.js
```

If the file has already been patched, `git apply` will fail. Reinstall the
plugin or restore the original `monitor.js`, then apply the patch again. The
script is idempotent and exits successfully when it detects the bridge patch is
already present.

## Run

From the BYOB repo root:

```powershell
.\openclaw\scripts\start-gateway.ps1
```

The default gateway endpoint is:

```text
http://127.0.0.1:18789
```

The script loads `openclaw/env.local`, sets `OPENCLAW_STATE_DIR`, and starts:

```text
openclaw gateway run --allow-unconfigured --port 18789 --bind loopback --auth none
```

## Bridge Environment Variables

| Name | Required | Default | Purpose |
| --- | --- | --- | --- |
| `BYOB_BRIDGE_ENABLED` | no | `1` | Enables bridge interception. |
| `BYOB_API_BASE_URL` | no | `http://127.0.0.1:8000` | BYOB API base URL. |
| `BYOB_API_TOKEN` | one auth mode | empty | Static BYOB bearer token. |
| `BYOB_API_EMAIL` | one auth mode | empty | BYOB login email. |
| `BYOB_API_PASSWORD` | one auth mode | empty | BYOB login password. |
| `BYOB_AGENT_USE_LLM` | no | `true` | Sends `use_llm` to `/api/v1/agent/ask`. |
| `BYOB_AGENT_TOP_K` | no | `5` | Retrieval `top_k`, clamped to 1..20. |
| `BYOB_BRIDGE_TIMEOUT_MS` | no | `180000` | Timeout for BYOB login and QA calls. |

## Notes

- Do not commit `env.local`, `state/`, logs, or installed packages.
- Do not store WeCom secrets or BYOB passwords in tracked files.
- `BYOB_AGENT_USE_LLM=false` keeps the bridge extractive and avoids LLM calls.
- `BYOB_AGENT_USE_LLM=true` uses the LLM configured in BYOB, not OpenClaw.
- The current patch is a pragmatic sidecar patch against plugin `2026.4.29`.
  For production, prefer moving this bridge into a first-class OpenClaw plugin
  instead of editing installed `dist` files.
