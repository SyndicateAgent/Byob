$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OpenClawRoot = Resolve-Path (Join-Path $ScriptDir "..")
$PluginDir = Join-Path $OpenClawRoot "state\npm\node_modules\@wecom\wecom-openclaw-plugin"
$PatchFile = Join-Path $OpenClawRoot "patches\wecom-monitor-byob-bridge.patch"
$MonitorFile = Join-Path $PluginDir "dist\src\monitor.js"

if (-not (Test-Path -LiteralPath $MonitorFile)) {
    throw "WeCom plugin monitor.js was not found. Run: npm install --prefix .\state\npm @wecom/wecom-openclaw-plugin@2026.4.29"
}

$monitorText = Get-Content -LiteralPath $MonitorFile -Raw
if ($monitorText -match "tryByobBridgeReply") {
    Write-Host "BYOB bridge patch is already applied."
} else {
    Push-Location $PluginDir
    try {
        git apply $PatchFile
    } finally {
        Pop-Location
    }
    Write-Host "BYOB bridge patch applied."
}

node --check $MonitorFile
