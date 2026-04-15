@echo off
cd /d "%~dp0"
echo ========================================
echo   Supabase Dataset Updater
echo ========================================
echo.
echo Starte Update des Supabase Datasets...
echo.

:: Prüfe ob .env Datei existiert
if not exist ".env" (
    echo WARNUNG: .env Datei nicht gefunden!
    echo Bitte erstelle eine .env Datei mit SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY
    echo.
    pause
    exit /b 1
)

:: Führe das Update-Script aus
pnpm run update

echo.
echo ========================================
echo   Update abgeschlossen!
echo ========================================
echo.
pause
