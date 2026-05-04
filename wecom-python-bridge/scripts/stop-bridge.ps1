$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgeRoot = Resolve-Path (Join-Path $ScriptDir "..")
$PidFile = Join-Path $BridgeRoot "bridge.pid"

if (Test-Path -LiteralPath $PidFile) {
    $pidText = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($pidText -match "^\d+$") {
        Stop-Process -Id ([int]$pidText) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "byob_wecom_bridge\.main" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Stopped BYOB WeCom Python bridge."
