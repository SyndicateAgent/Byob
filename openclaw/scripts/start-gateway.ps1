param(
    [int]$Port = 18789,
    [string]$Bind = "loopback",
    [string]$Auth = "none"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OpenClawRoot = Resolve-Path (Join-Path $ScriptDir "..")
$StateDir = Join-Path $OpenClawRoot "state"
$EnvFile = Join-Path $OpenClawRoot "env.local"

function Import-LocalEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
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

function Set-DefaultEnv {
    param([string]$Name, [string]$Value)

    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

Import-LocalEnv -Path $EnvFile

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$env:OPENCLAW_STATE_DIR = $StateDir

Set-DefaultEnv "BYOB_BRIDGE_ENABLED" "1"
Set-DefaultEnv "BYOB_API_BASE_URL" "http://127.0.0.1:8000"
Set-DefaultEnv "BYOB_AGENT_USE_LLM" "true"
Set-DefaultEnv "BYOB_AGENT_TOP_K" "5"
Set-DefaultEnv "BYOB_BRIDGE_TIMEOUT_MS" "180000"

$OpenClawCmd = Join-Path $OpenClawRoot "node_modules\.bin\openclaw.cmd"
if (-not (Test-Path -LiteralPath $OpenClawCmd)) {
    throw "OpenClaw CLI was not found. Run `npm install` from $OpenClawRoot first."
}

& $OpenClawCmd gateway run --allow-unconfigured --port $Port --bind $Bind --auth $Auth
