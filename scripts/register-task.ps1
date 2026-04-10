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

function New-LogonTaskDefinition {
    return @{
        Trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
        Principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
        TriggerLabel = "At user logon ($currentUser)"
    }
}

function New-StartupTaskDefinition {
    return @{
        Trigger = New-ScheduledTaskTrigger -AtStartup
        Principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType S4U -RunLevel Highest
        TriggerLabel = "At startup (requires permissions)"
    }
}

if ($AtStartup) {
    $taskDefinition = New-StartupTaskDefinition
} else {
    $taskDefinition = New-LogonTaskDefinition
}

$trigger = $taskDefinition.Trigger
$principal = $taskDefinition.Principal
$triggerLabel = $taskDefinition.TriggerLabel
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Starts Lyft Price Tracker API automatically." -Force -ErrorAction Stop
    Write-Host "Task '$TaskName' registered successfully."
    Write-Host "Trigger: $triggerLabel"
    Write-Host "It will launch the app on http://${BindHost}:$Port"
} catch {
    $errorMessage = $_.Exception.Message
    $isAccessDenied = $errorMessage -match "Access is denied|0x80070005"

    if ($AtStartup -and $isAccessDenied) {
        Write-Warning "Could not create an AtStartup task due to missing elevation. Falling back to user logon trigger."

        $taskDefinition = New-LogonTaskDefinition
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $taskDefinition.Trigger -Principal $taskDefinition.Principal -Settings $settings -Description "Starts Lyft Price Tracker API automatically." -Force -ErrorAction Stop

        Write-Host "Task '$TaskName' registered successfully."
        Write-Host "Trigger: $($taskDefinition.TriggerLabel)"
        Write-Host "It will launch the app on http://${BindHost}:$Port"
        return
    }

    Write-Error "Failed to register task '$TaskName': $errorMessage"
    exit 1
}
