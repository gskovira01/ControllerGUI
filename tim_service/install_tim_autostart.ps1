# install_tim_autostart.ps1
# =============================================================================
# Registers the TIM Motion Service as a Windows Task Scheduler task on iPC400.
# Run this script ONCE on the iPC400 as Administrator to set up auto-start.
#
# The task fires at user logon (requires auto-logon to be configured on iPC400)
# with a 30-second delay so INtime and EtherCAT finish initializing first.
# The service then waits another startup_delay_sec (tim_config.yaml) before
# connecting RapidCode -- the two delays stack for reliable cold-boot startup.
#
# Running as the logged-in user (not SYSTEM) allows the status/stop GUI window
# to appear on the desktop.
#
# To uninstall:  Unregister-ScheduledTask -TaskName "TIM Motion Service" -Confirm:$false
# To run now:    Start-ScheduledTask -TaskName "TIM Motion Service"
# =============================================================================

$TaskName    = "TIM Motion Service"
$ServiceRoot = "C:\TIM\ControllerGUI\tim_service"
$Script      = "$ServiceRoot\start_tim_service.ps1"

if (-not (Test-Path $Script)) {
    Write-Error "start_tim_service.ps1 not found at $Script. Check that files are in C:\TIM\ControllerGUI\tim_service."
    exit 1
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy RemoteSigned -NonInteractive -File `"$Script`"" `
    -WorkingDirectory $ServiceRoot

# Trigger: at logon of any user, with a 30-second delay for INtime/EtherCAT.
# AtLogon (rather than AtStartup) lets the task run in the user's desktop
# session so the tkinter status window can appear.
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Trigger.Delay = "PT30S"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 24) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

# Run as the current (admin) user so the GUI window appears on the desktop.
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task: $TaskName"
}

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Trigger   $Trigger `
    -Settings  $Settings `
    -Principal $Principal `
    -Description "TIM Motion Service - auto-starts RapidCode/EtherCAT motion gateway on iPC400 boot."

Write-Host ""
Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "The service will start automatically 30 seconds after logon."
Write-Host ""
Write-Host "To test immediately: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host 'To remove:           Unregister-ScheduledTask -TaskName "TIM Motion Service" -Confirm:$false'
