param([switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$modelUrl = 'http://127.0.0.1:8766'
$candidates = @((Join-Path $repoRoot '.venv\Scripts\python.exe'), (Join-Path (Split-Path -Parent $repoRoot) 'work\ccare-venv\Scripts\python.exe'))
$modelPython = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $modelPython) { throw 'Python environment missing. See the local guide.' }
& $modelPython (Join-Path $PSScriptRoot 'check_model.py')
if ($LASTEXITCODE -ne 0) { throw 'Complete backend/.env.local with a fresh key. No external request was sent.' }
try { $health = Invoke-RestMethod -Uri "$modelUrl/ping" -TimeoutSec 2 } catch { $health = $null }
if ($health -and ($health.mode -ne 'remote' -or $health.conversation_storage -ne 'none')) { throw 'Port 8766 is in use by another service. No process was stopped.' }
if (-not $health) {
    $logDir = Join-Path $repoRoot 'work\model-logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $process = Start-Process -FilePath $modelPython -ArgumentList @('start.py','--mode','remote','--port','8766') -WorkingDirectory (Join-Path $repoRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "$stamp.stdout.log") -RedirectStandardError (Join-Path $logDir "$stamp.stderr.log")
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $health = Invoke-RestMethod -Uri "$modelUrl/ping" -TimeoutSec 2 } catch { $health = $null }
        if ($health) { break }
        if ($process.HasExited) { throw "Startup failed. Check $logDir" }
    }
    if (-not $health -or $health.mode -ne 'remote') { throw "Startup failed. Check $logDir" }
}
Write-Output "KinVoice model website is ready: $modelUrl"
if (-not $NoOpen) { Start-Process $modelUrl }
