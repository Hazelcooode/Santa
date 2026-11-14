param([int]$Port = 239, [switch]$Reload)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $repoPath '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
    & $pythonPath -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
Push-Location $PSScriptRoot
try {
    $serverArgs = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port")
    if ($Reload) { $serverArgs += '--reload' }
    & $pythonPath @serverArgs
} finally { Pop-Location }
