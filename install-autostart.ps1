# Makes the bot start hidden every time you log in to Windows, and starts it now.
# Undo with:  .\install-autostart.ps1 -Remove
param([switch]$Remove)
$name = 'GTA6 Shorts Bot'

if ($Remove) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -like '*bot.py*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Write-Output 'Auto-start removed and bot stopped.'
    return
}

$script = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'run-bot.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Runs the GTA 6 shorts Telegram bot in the background' -Force | Out-Null
Start-ScheduledTask -TaskName $name
Write-Output "Installed. The bot now runs in the background and starts when you log in."
