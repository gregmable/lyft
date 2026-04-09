param(
    [string]$ProjectPath,
    [string]$PythonExe = "python",
    [string]$Host = "127.0.0.1",
    [int]$Port = 8000
)

if (-not $ProjectPath) {
    $ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

Set-Location $ProjectPath

# Launch the FastAPI server in production mode for scheduled startup.
& $PythonExe -m uvicorn app.main:app --host $Host --port $Port
