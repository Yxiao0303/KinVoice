param([switch]$NoOpen, [ValidateRange(1024,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$demoUrl = "http://127.0.0.1:$Port"
function Read-DemoHealth {
    try { return Invoke-RestMethod -Uri "$demoUrl/ping" -TimeoutSec 2 } catch { return $null }
}
$health = Read-DemoHealth
if ($health) {
    if ($health.mode -ne 'demo' -or $health.conversation_storage -ne 'none') {
        throw "Port $Port is already serving another mode. No process was stopped. Choose another -Port."
    }
    if ($health.progress_stream -ne 'ccare-stream-v1') { throw "An earlier demo version uses port $Port. Keep it running and start this version with -Port 8768 (or another free port)." }
} else {
    $candidates = @(
        (Join-Path $repoRoot '.venv\Scripts\python.exe'),
        (Join-Path (Split-Path -Parent $repoRoot) 'work\ccare-venv\Scripts\python.exe')
    )
    $demoPython = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $demoPython) { throw 'Python environment missing. Follow docs/WEBSITE_DEMO_2026-10-23.md to install the pinned dependencies.' }
    $logDir = Join-Path $repoRoot 'work\demo-logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $process = Start-Process -FilePath $demoPython -ArgumentList @('start.py', '--mode', 'demo', '--port', "$Port") -WorkingDirectory (Join-Path $repoRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "$stamp.stdout.log") -RedirectStandardError (Join-Path $logDir "$stamp.stderr.log")
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 300
        $health = Read-DemoHealth
        if ($health) { break }
        if ($process.HasExited) { throw "Demo startup failed. Check $logDir" }
    }
    if (-not $health -or $health.mode -ne 'demo' -or $health.conversation_storage -ne 'none') { throw "Demo health check failed. Check $logDir" }
}
Write-Output "KinVoice demo is ready: $demoUrl"
if (-not $NoOpen) { Start-Process $demoUrl }
