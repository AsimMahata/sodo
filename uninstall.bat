@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ======================================================================
echo   SODO - YouTube -^> MP3 Downloader CLI (Uninstaller)
echo ======================================================================
echo.
echo [!] Tips:
echo     - If uninstallation fails due to permissions, run with 'sudow uninstall.bat'
echo     - If you don't have sudow, install it via 'tom install sudow'
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
where pip >nul 2>nul
if %ERRORLEVEL% equ 0 (
    pip uninstall -y sodo
) else (
    py -m pip uninstall -y sodo
)
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Uninstallation failed. If this is a permission issue, run with 'sudow uninstall.bat' (or install sudow via 'tom install sudow').
    exit /b 1
)

echo.
echo ======================================================================
echo   [+] Successfully uninstalled sodo.
echo ======================================================================
echo.
