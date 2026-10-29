<#
.SYNOPSIS
    Start the DocQA backend and frontend for local development, then seed the demo workspace.

.DESCRIPTION
    Opens the backend (uvicorn with --reload, port 8000) and the frontend (Vite, port 5173) in
    their own PowerShell windows, waits until the backend's /health answers, then runs
    `uv run python -m scripts.seed_demo` (safe to repeat: it only adds what is missing).

    Press Ctrl+C here to stop both servers. Closing a server's window stops that server.
    A server that is already running on its port is reused, not started twice.

    Run from anywhere:
        powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#>
param(
    # How long to wait for the backend; the first start loads the embedding model
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
# 127.0.0.1, not localhost: Windows PowerShell tries IPv6 (::1) first, and uvicorn only listens
# on IPv4, so a localhost check times out even while the backend is up
$HealthUrl = 'http://127.0.0.1:8000/health'
$AppUrl = 'http://localhost:5173'

function Test-Url([string]$Url) {
    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Start-ServerWindow([string]$Title, [string]$Directory, [string]$Command) {
    # -NoExit keeps the window open if the server crashes, so its error stays readable
    $script = "`$Host.UI.RawUI.WindowTitle = 'DocQA $Title'; $Command"
    Start-Process powershell -WorkingDirectory $Directory -PassThru `
        -ArgumentList '-NoProfile', '-NoExit', '-Command', $script
}

function Stop-ServerWindow($Process) {
    if ($Process -and -not $Process.HasExited) {
        # /T stops the whole tree: the window's shell, uvicorn's reloader and worker, or node
        taskkill /PID $Process.Id /T /F | Out-Null
    }
}

foreach ($tool in 'uv', 'npm') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "'$tool' is not on PATH. Install it (or open a new terminal after installing)."
    }
}
if (-not (Test-Path (Join-Path $Backend '.venv'))) {
    throw "backend\.venv is missing. Run 'uv sync' in backend\ first."
}
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    throw "frontend\node_modules is missing. Run 'npm install' in frontend\ first."
}
if (-not (Test-Path (Join-Path $Backend '.env'))) {
    Write-Warning "backend\.env not found: copy backend\.env.example to backend\.env and add your API key."
}

$backendProcess = $null
$frontendProcess = $null
try {
    if (Test-Url $HealthUrl) {
        Write-Host 'Backend already running on :8000, reusing it.'
    } else {
        Write-Host 'Starting backend on :8000 ...'
        $backendProcess = Start-ServerWindow 'backend' $Backend `
            'uv run uvicorn app.main:create_app --factory --port 8000 --reload'
    }
    if (Test-Url $AppUrl) {
        Write-Host 'Frontend already running on :5173, reusing it.'
    } else {
        Write-Host 'Starting frontend on :5173 ...'
        $frontendProcess = Start-ServerWindow 'frontend' $Frontend 'npm run dev'
    }

    Write-Host -NoNewline 'Waiting for the backend'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not (Test-Url $HealthUrl)) {
        if ($backendProcess -and $backendProcess.HasExited) {
            throw 'The backend window was closed before the API came up.'
        }
        if ((Get-Date) -gt $deadline) {
            throw "The backend did not answer $HealthUrl within $TimeoutSeconds seconds. Check its window."
        }
        Write-Host -NoNewline '.'
        Start-Sleep -Seconds 1
    }
    Write-Host ' ready.'

    Write-Host 'Seeding the demo workspace ...'
    Push-Location $Backend
    try {
        uv run python -m scripts.seed_demo
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Seeding failed (see above); the servers keep running.' }
    } finally {
        Pop-Location
    }

    Write-Host ''
    Write-Host "DocQA is running at $AppUrl"
    if (-not ($backendProcess -or $frontendProcess)) {
        Write-Host 'Both servers were already running, so there is nothing for this script to stop.'
        return
    }
    Write-Host 'Press Ctrl+C to stop the servers this script started.'
    # Wait until the user presses Ctrl+C (runs the finally block) or closes the server windows
    while (($backendProcess -and -not $backendProcess.HasExited) -or
           ($frontendProcess -and -not $frontendProcess.HasExited)) {
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-ServerWindow $backendProcess
    Stop-ServerWindow $frontendProcess
}
