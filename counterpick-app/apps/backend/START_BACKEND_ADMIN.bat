@echo off
:: Prüfe ob bereits als Admin ausgeführt
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Bereits als Administrator ausgefuehrt.
) else (
    echo Fordere Administratorrechte an...
    :: Starte PowerShell-Skript als Admin
    cd /d "%~dp0"
    powershell -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -NoExit -File \"%~dp0start.ps1\"'"
    exit /b
)

:: Falls bereits als Admin, starte PowerShell-Skript direkt
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0start.ps1"
pause

