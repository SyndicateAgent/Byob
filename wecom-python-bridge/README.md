# BYOB WeCom Python Bridge

Chinese documentation: [README.zh-CN.md](./README.zh-CN.md).

This directory contains the Python alternative to the OpenClaw sidecar. It uses
Enterprise WeChat's intelligent robot long-connection SDK as a WebSocket client,
then forwards text messages to BYOB's `POST /api/v1/agent/ask`.

This bridge does not start OpenClaw, does not patch OpenClaw plugins, and does
not require a public webhook URL in long-connection mode.

## Quick Start

```powershell
cd .\wecom-python-bridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .\env.example .\env.local
```

Fill `env.local` with the WeCom Bot ID/Secret and BYOB auth settings. Do not
commit `env.local`.

Run in a visible terminal:

```powershell
.\scripts\start-bridge.ps1
```

Run hidden in the background:

```powershell
.\scripts\start-bridge-hidden.ps1
```

Stop the background bridge:

```powershell
.\scripts\stop-bridge.ps1
```

Logs are written to `logs/`. The hidden starter writes `bridge.pid`.

## Notes

- OpenClaw should stay stopped while this Python bridge is active.
- `BYOB_AGENT_USE_LLM=true` uses BYOB's configured LLM.
- `BYOB_AGENT_USE_LLM=false` verifies BYOB retrieval without LLM generation.
- Enterprise WeChat Bot ID/Secret must be created manually by a human admin in
  the Enterprise WeChat console.
