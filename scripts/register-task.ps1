param(
    [string]$TaskName = "LyftPriceTracker",
    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$AtStartup
)

$projectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runnerScript = Join-Path $projectPath "scripts\run-server.ps1"

if (-not (Test-Path $runnerScript)) {
    throw "Runner script not found at $runnerScript"
}

$venvPython = Join-Path $projectPath ".venv\Scripts\python.exe"
if (-not $PythonExe -and (Test-Path $venvPython)) {
    $PythonExe = $venvPython
}

$argString = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`" -ProjectPath `"$projectPath`" -BindHost `"$BindHost`" -Port $Port"
if ($PythonExe) {
    $argString += " -PythonExe `"$PythonExe`""
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argString
$currentUser = "$env:USERDOMAIN\$env:USERNAME"
if ($AtStartup) {
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType S4U -RunLevel Highest
} else {
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
}
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Starts Lyft Price Tracker API automatically." -Force -ErrorAction Stop
    Write-Host "Task '$TaskName' registered successfully."
    if ($AtStartup) {
        Write-Host "Trigger: At startup (requires permissions)."
    } else {
        Write-Host "Trigger: At user logon ($currentUser)."
    }
    Write-Host "It will launch the app on http://${BindHost}:$Port"
} catch {
    Write-Error "Failed to register task '$TaskName': $($_.Exception.Message)"
    exit 1
}
