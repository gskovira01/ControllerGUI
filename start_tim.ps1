param(
    [switch]$ServiceOnly,
    [switch]$GuiOnly
)

# [CHANGE 2026-04-17 20:25:00 -04:00] Unified launcher for TIM service and ControllerGUI.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serviceDir = Join-Path $scriptDir "tim_service"
$guiScript = Join-Path $scriptDir "ControllerGUI.py"

$pythonCandidates = @(
    (Join-Path $scriptDir "venv_rmp311\Scripts\python.exe"),
    (Join-Path $scriptDir "venv_py310\Scripts\python.exe"),
    (Join-Path $scriptDir "venv_rmp39\Scripts\python.exe"),
    (Join-Path $scriptDir ".venv\Scripts\python.exe")
)

$pythonExe = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    Write-Error "No Python venv found. Checked: $($pythonCandidates -join ', ')"
    exit 1
}

if ((-not $GuiOnly) -and (-not (Test-Path $serviceDir))) {
    Write-Error "tim_service folder not found at $serviceDir"
    exit 1
}

if ((-not $ServiceOnly) -and (-not (Test-Path $guiScript))) {
    Write-Error "ControllerGUI.py not found at $guiScript"
    exit 1
}

if (-not $GuiOnly) {
    Write-Host "[TIM] Starting service in a new PowerShell window..."

    $serviceCmd = "`$env:PATH='C:\RSI\11.0.3;C:\Program Files (x86)\INtime\bin;' + `$env:PATH; Set-Location '$serviceDir'; & '$pythonExe' 'tim_motion_service.py' --config 'tim_config.yaml' --host '0.0.0.0' --port '503' --gui"

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $serviceCmd
    ) | Out-Null
}

if (-not $ServiceOnly) {
    Write-Host "[TIM] Launching ControllerGUI..."
    & $pythonExe $guiScript
}
