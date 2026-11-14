# ============================================================
#  PlanWise AI - Start Script
#  Launches Backend (FastAPI) and Frontend (Vite) in separate
#  PowerShell windows so both run side-by-side.
#
#  Usage:   .\start.ps1
# ============================================================

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   PlanWise AI - Startup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

function Test-PortFree([int]$Port) {
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Find-FreePort([int]$Preferred) {
    for ($p = $Preferred; $p -lt ($Preferred + 30); $p++) {
        if (Test-PortFree $p) { return $p }
    }
    return $Preferred
}

# -- 1. Load .env (create it from the example on first run) ----
$envFile = Join-Path $ROOT ".env"
$envExample = Join-Path $ROOT ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "[.env] Created .env from .env.example." -ForegroundColor Green
}

$hasLlmKey = $false
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            $key   = $matches[1].Trim()
            $value = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
            if ($key -match '^(GROQ|GEMINI|OPENROUTER|CUSTOM_LLM)_API_KEY$' -and $value) { $hasLlmKey = $true }
        }
    }
    Write-Host "[.env] Loaded environment variables." -ForegroundColor Green
} else {
    Write-Warning ".env file not found at $envFile -- using defaults."
}

if (-not $hasLlmKey) {
    Write-Host ""
    Write-Host "[LLM] No API key found - running in free keyless mode" -ForegroundColor Yellow
    Write-Host "      (about one AI reply every 45 seconds, and slow)." -ForegroundColor Yellow
    Write-Host "      For fast answers add a FREE key to .env, e.g.:" -ForegroundColor Yellow
    Write-Host "        GROQ_API_KEY=...    https://console.groq.com/keys" -ForegroundColor Yellow
    Write-Host "        GEMINI_API_KEY=...  https://aistudio.google.com/apikey" -ForegroundColor Yellow
    Write-Host ""
}

$backendHost = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "0.0.0.0" }
$wantedBackendPort = if ($env:BACKEND_PORT) { [int]$env:BACKEND_PORT } else { 8000 }

# -- 2. Pick free ports (another app may already use 8000/3000) -
$backendPort = Find-FreePort $wantedBackendPort
if ($backendPort -ne $wantedBackendPort) {
    Write-Host "[Port] $wantedBackendPort is in use by another program - backend will use $backendPort." -ForegroundColor Yellow
}
$frontendPort = Find-FreePort 3000
if ($frontendPort -ne 3000) {
    Write-Host "[Port] 3000 is in use by another program - frontend will use $frontendPort." -ForegroundColor Yellow
}

# -- 3. Paths -------------------------------------------------
$backendDir  = Join-Path $ROOT "backend"
$frontendDir = Join-Path $ROOT "frontend-web"

# -- 4. Check Python ------------------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Host "[ERROR] Python not found. Please install Python 3.9+ and add it to PATH." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
$pythonExe = $python.Source
Write-Host "[Python] Found: $pythonExe" -ForegroundColor Green

# -- 5. Check Node / npm --------------------------------------
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Host "[ERROR] npm not found. Please install Node.js (https://nodejs.org) and add it to PATH." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[Node]   Found: npm $(npm --version)" -ForegroundColor Green

# -- 6. Install / update backend dependencies -----------------
Write-Host ""
Write-Host "[Backend] Installing Python dependencies..." -ForegroundColor Yellow
$reqFile = Join-Path $backendDir "requirements.txt"
if (Test-Path $reqFile) {
    & $pythonExe -m pip install -r $reqFile --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Backend] pip install failed. Check requirements.txt." -ForegroundColor Red
    } else {
        Write-Host "[Backend] Dependencies OK." -ForegroundColor Green
    }
} else {
    Write-Warning "requirements.txt not found at $reqFile -- skipping pip install."
}

# -- 7. Install frontend dependencies -------------------------
Write-Host ""
Write-Host "[Frontend] Checking Node dependencies..." -ForegroundColor Yellow
$viteBin = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
if (-not (Test-Path $viteBin)) {
    Push-Location $frontendDir
    npm install --silent
    Pop-Location
    Write-Host "[Frontend] npm install done." -ForegroundColor Green
} else {
    Write-Host "[Frontend] node_modules already present -- skipping npm install." -ForegroundColor Green
}

# -- 8. Launch Backend in a new window ------------------------
Write-Host ""
Write-Host "[Backend] Starting FastAPI on http://localhost:$backendPort ..." -ForegroundColor Cyan

$backendCmd = "Set-Location '$backendDir'; " +
              "`$env:BACKEND_PORT = '$backendPort'; " +
              "Write-Host 'PlanWise AI -- Backend' -ForegroundColor Cyan; " +
              "& '$pythonExe' -m uvicorn app.main:app --host $backendHost --port $backendPort --reload; " +
              "Read-Host 'Backend stopped. Press Enter to close'"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd `
    -WorkingDirectory $backendDir

# Wait until the backend answers (the first start loads the search index)
Write-Host "[Backend] Waiting for the API to come up..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$backendPort/api/v1/health" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200 -and $r.Content -match 'planwise-api') { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if ($ready) {
    Write-Host "[Backend] API is up." -ForegroundColor Green
} else {
    Write-Host "[Backend] Still starting - check the backend window for errors." -ForegroundColor Yellow
}

# -- 9. Launch Frontend in a new window -----------------------
Write-Host "[Frontend] Starting Vite dev server on http://localhost:$frontendPort ..." -ForegroundColor Cyan

# BACKEND_PORT tells the Vite proxy where the API lives
$frontendCmd = "Set-Location '$frontendDir'; " +
               "`$env:BACKEND_PORT = '$backendPort'; " +
               "Write-Host 'PlanWise AI -- Frontend' -ForegroundColor Cyan; " +
               "npm run dev -- --port $frontendPort --strictPort; " +
               "Read-Host 'Frontend stopped. Press Enter to close'"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd `
    -WorkingDirectory $frontendDir

# -- 10. Done -------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Both servers are launching!" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend --> http://localhost:$frontendPort" -ForegroundColor White
Write-Host "  Backend  --> http://localhost:$backendPort" -ForegroundColor White
Write-Host "  API Docs --> http://localhost:${backendPort}/docs" -ForegroundColor White
Write-Host ""
Write-Host "  Close the individual terminal windows" -ForegroundColor DarkGray
Write-Host "  to stop each server." -ForegroundColor DarkGray
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
