# Counterpick Backend Start Script (PowerShell)
# Fehlerbehandlung: Skript nicht bei Fehlern beenden
$ErrorActionPreference = "Continue"

# Prüfe ob bereits als Admin ausgeführt
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Fordere Administratorrechte an..." -ForegroundColor Yellow
    try {
        $scriptPath = $PSCommandPath
        Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$scriptPath`""
    } catch {
        Write-Host "FEHLER beim Anfordern der Administratorrechte: $_" -ForegroundColor Red
        Write-Host "Versuche ohne Admin-Rechte zu starten..." -ForegroundColor Yellow
    }
    # Warte kurz, damit das neue Fenster geöffnet werden kann
    Start-Sleep -Seconds 1
    exit
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "COUNTERPICK FLASK BACKEND STARTER (ALS ADMINISTRATOR)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Wechsle ins Script-Verzeichnis
Set-Location $PSScriptRoot

# Prüfe Python-Installation
Write-Host "Pruefe Python-Installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python nicht gefunden"
    }
    Write-Host $pythonVersion -ForegroundColor Green
} catch {
    Write-Host "FEHLER: Python ist nicht installiert oder nicht im PATH!" -ForegroundColor Red
    Write-Host "Fehlerdetails: $_" -ForegroundColor Red
    Read-Host "Druecke Enter zum Beenden"
    exit 1
}

# Prüfe Dependencies
Write-Host ""
Write-Host "Pruefe Dependencies..." -ForegroundColor Yellow
try {
    python -c "import flask_cors" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "flask_cors nicht gefunden"
    }
    Write-Host "Alle Dependencies sind bereits installiert." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "Installiere fehlende Dependencies aus requirements.txt..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FEHLER beim Installieren der Dependencies!" -ForegroundColor Red
        Read-Host "Druecke Enter zum Beenden"
        exit 1
    }
    Write-Host ""
}

# Prüfe lolalytics_api Paket
Write-Host ""
Write-Host "Pruefe lolalytics_api Paket..." -ForegroundColor Yellow
try {
    python -c "import lolalytics_api" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "lolalytics_api nicht gefunden"
    }
    Write-Host "lolalytics_api Paket ist bereits installiert." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "Installiere lolalytics_api Paket (editable mode)..." -ForegroundColor Yellow
    pip install -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FEHLER beim Installieren des lolalytics_api Pakets!" -ForegroundColor Red
        Read-Host "Druecke Enter zum Beenden"
        exit 1
    }
    Write-Host ""
}

# Prüfe .env Variablen
Write-Host ""
Write-Host "Pruefe .env Variablen (SUPABASE_URL / SERVICE_ROLE / ANON)..." -ForegroundColor Yellow
python -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(dotenv_path=Path('.') / '.env'); import os; print('SUPABASE_URL:', os.getenv('SUPABASE_URL')); print('SUPABASE_SERVICE_ROLE_KEY gesetzt:', bool(os.getenv('SUPABASE_SERVICE_ROLE_KEY'))); print('SUPABASE_ANON_KEY gesetzt:', bool(os.getenv('SUPABASE_ANON_KEY')))"

# Aktiviere venv falls vorhanden
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host ""
    Write-Host "Aktiviere Virtual Environment..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
}

Write-Host ""
Write-Host "Starte Backend mit Administratorrechten..." -ForegroundColor Green
Write-Host "Server laeuft auf http://localhost:5000" -ForegroundColor Green
Write-Host ""

try {
    python backend.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nBackend wurde mit Fehlercode $LASTEXITCODE beendet." -ForegroundColor Red
    }
} catch {
    Write-Host "`nFEHLER beim Starten des Backends: $_" -ForegroundColor Red
    Write-Host "Stack Trace: $($_.ScriptStackTrace)" -ForegroundColor Red
} finally {
    Write-Host ""
    Read-Host "Druecke Enter zum Beenden"
}

