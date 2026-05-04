param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgeRoot = Resolve-Path (Join-Path $ScriptDir "..")
$EnvFile = Join-Path $BridgeRoot "env.local"

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

Push-Location $BridgeRoot
try {
    & $PythonPath -m byob_wecom_bridge.main
} finally {
    Pop-Location
}
