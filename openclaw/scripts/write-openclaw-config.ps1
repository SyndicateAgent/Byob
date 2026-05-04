$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OpenClawRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $OpenClawRoot "..")
$StateDir = Join-Path $OpenClawRoot "state"
$EnvFile = Join-Path $OpenClawRoot "env.local"
$ConfigFile = Join-Path $StateDir "openclaw.json"
$PluginDir = Join-Path $OpenClawRoot "state\npm\node_modules\@wecom\wecom-openclaw-plugin"

function Import-LocalEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "env.local was not found. Copy env.example to env.local and fill in WeCom/BYOB values first."
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $index = $trimmed.IndexOf("=")
        if ($index -le 0) {
            continue
        }
        $name = $trimmed.Substring(0, $index).Trim()
        $value = $trimmed.Substring($index + 1).Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Require-Env {
    param([string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not $value) {
        throw "$Name is required in env.local"
    }
    return $value
}

Import-LocalEnv -Path $EnvFile

$botId = Require-Env "WECOM_BOT_ID"
$secret = Require-Env "WECOM_SECRET"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

$config = [ordered]@{
    plugins = [ordered]@{
        entries = [ordered]@{
            "wecom-openclaw-plugin" = [ordered]@{
                enabled = $true
            }
        }
        load = [ordered]@{
            paths = @($PluginDir)
        }
        allow = @(
            "wecom-openclaw-plugin",
            "memory-core"
        )
    }
    channels = [ordered]@{
        wecom = [ordered]@{
            enabled = $true
            botId = $botId
            secret = $secret
            sendThinkingMessage = $true
            connectionMode = "websocket"
        }
    }
    mcp = [ordered]@{
        servers = [ordered]@{
            byob = [ordered]@{
                url = "http://127.0.0.1:8010/mcp"
                transport = "streamable-http"
            }
        }
    }
    tools = [ordered]@{
        alsoAllow = @("wecom_mcp")
    }
}

$config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ConfigFile -Encoding UTF8
Write-Host "Wrote $ConfigFile for BYOB repo $RepoRoot"
