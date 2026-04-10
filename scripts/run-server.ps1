param(
    [string]$ProjectPath,
    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

if (-not $ProjectPath) {
    $ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

Set-Location $ProjectPath

if (-not $PythonExe) {
    $venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = "python"
    } else {
        throw "No Python interpreter found. Set -PythonExe or create .venv."
    }
}

# Launch the FastAPI server in production mode for scheduled startup.
& $PythonExe -m uvicorn app.main:app --host $BindHost --port $Port
