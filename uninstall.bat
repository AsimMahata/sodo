@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ======================================================================
echo   SODO - YouTube -^> MP3 Downloader CLI (Uninstaller)
echo ======================================================================
echo.

if "%1" neq "-y" if "%1" neq "--yes" (
    set /p "CONFIRM=Are you sure you want to uninstall sodo? [Y/n]: "
    if /i "!CONFIRM!"=="n" (
        echo [!] Uninstallation cancelled.
        exit /b 0
    )
)

echo.
echo [*] Removing sodo package...
powershell -NoProfile -Command "pip uninstall -y sodo"
echo.
echo ======================================================================
echo   [+] Successfully uninstalled sodo.
echo ======================================================================
echo.
