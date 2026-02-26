@echo off
cd /d "%~dp0"
echo ========================================
echo   Vue Frontend - Dev Server Starter
echo ========================================
echo.
echo Starte Vue Frontend auf Port 3000...
echo.

:: Öffne Browser nach kurzer Verzögerung im Hintergrund
powershell -Command "Start-Sleep -Seconds 4; Start-Process 'http://localhost:3000'"

:: Starte den Dev-Server (läuft bis Strg+C gedrückt wird)
echo Browser wird automatisch geoeffnet...
echo Zum Beenden: Strg+C druecken
echo.
pnpm dev


