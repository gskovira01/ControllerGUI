# [CHANGE 2026-04-17 20:32:00 -04:00] Wrapper entry point delegates to unified launcher.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $scriptDir "start_tim.ps1"

if (-not (Test-Path $launcher)) {
    Write-Error "Unified launcher not found at $launcher"
    exit 1
}

& $launcher -ServiceOnly