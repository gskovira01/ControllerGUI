# start_tim_service.ps1
# Self-contained launcher for the TIM Motion Service.
# Lives in tim_service\ and is called by the Task Scheduler task registered
# by install_tim_autostart.ps1.  The venv is expected one level up in the
# ControllerGUI repo root.

$serviceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot   = Split-Path -Parent $serviceDir

$pythonCandidates = @(
    (Join-Path $repoRoot "venv_rmp311\Scripts\python.exe"),
    (Join-Path $repoRoot "venv_py310\Scripts\python.exe"),
    (Join-Path $repoRoot "venv_rmp39\Scripts\python.exe"),
    (Join-Path $repoRoot ".venv\Scripts\python.exe")
)

$pythonExe = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    Write-Error "No Python venv found under $repoRoot. Checked: $($pythonCandidates -join ', ')"
    exit 1
}

$env:PATH = "C:\RSI\11.0.3;C:\Program Files (x86)\INtime\bin;" + $env:PATH

Set-Location $serviceDir

& $pythonExe "tim_motion_service.py" --config "tim_config.yaml" --host "0.0.0.0" --port "503" --gui
