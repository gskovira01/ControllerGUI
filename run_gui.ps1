# [CHANGE 2026-04-11 12:40:00 -05:00] Use workspace-local venv_rmp311 for GUI launch.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$scriptDir\venv_rmp311\Scripts\python.exe" "$scriptDir\ControllerGUI.py"
