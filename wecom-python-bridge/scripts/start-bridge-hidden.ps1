param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgeRoot = Resolve-Path (Join-Path $ScriptDir "..")
$EnvFile = Join-Path $BridgeRoot "env.local"
$LogDir = Join-Path $BridgeRoot "logs"
$OutLog = Join-Path $LogDir "bridge.out.log"
$ErrLog = Join-Path $LogDir "bridge.err.log"
$PidFile = Join-Path $BridgeRoot "bridge.pid"

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "env.local was not found. Copy env.example to env.local and fill in WeCom/BYOB values first."
}

if ([IO.Path]::IsPathRooted($Python)) {
    $PythonPath = $Python
} else {
    $PythonPath = Join-Path $BridgeRoot $Python
}

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python runtime was not found at $PythonPath. Create a venv and install the bridge first."
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "byob_wecom_bridge\.main" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$proc = Start-Process `
    -FilePath $PythonPath `
    -ArgumentList @("-m", "byob_wecom_bridge.main") `
    -WorkingDirectory $BridgeRoot `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $proc.Id -Encoding ASCII
Write-Host "Started BYOB WeCom Python bridge in a hidden window. PID: $($proc.Id)"
Write-Host "Logs: $ErrLog"
