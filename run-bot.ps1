# Keeps the bot running: restarts it if it crashes or loses the internet.
# Started hidden at log-on by the "GTA6 Shorts Bot" scheduled task (see install-autostart.ps1).
$app = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = 'C:\gta6bot\.venv\Scripts\python.exe'
Set-Location $app
while ($true) {
    & $py bot.py
    if ($LASTEXITCODE -eq 3) { break }  # another copy is already running
    Start-Sleep -Seconds 20
}
