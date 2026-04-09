param(
    [string]$TaskName = "LyftPriceTracker",
    [string]$PythonExe = "python",
    [string]$Host = "127.0.0.1",
    [int]$Port = 8000
)

$projectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runnerScript = Join-Path $projectPath "scripts\run-server.ps1"

if (-not (Test-Path $runnerScript)) {
    throw "Runner script not found at $runnerScript"
}

$argString = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`" -ProjectPath `"$projectPath`" -PythonExe `"$PythonExe`" -Host `"$Host`" -Port $Port"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argString
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Starts Lyft Price Tracker API at system startup." -Force

Write-Host "Task '$TaskName' registered successfully."
Write-Host "It will launch the app at startup on http://$Host:$Port"
