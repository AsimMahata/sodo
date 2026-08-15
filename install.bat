@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ======================================================================
echo   SODO - YouTube -^> MP3 Downloader CLI (Installer)
echo ======================================================================
echo.
echo [*] Requirements:
echo     - Python 3.10+ in PATH
echo     - pip in PATH
echo     - FFmpeg (placed in tools/sodo/bin/ or in PATH for audio conversion)
echo.
echo [*] Tips:
echo     - Downloads high quality audio with ID3 metadata tags
echo     - Run 'sodo --help' to see quick-start commands
echo     - Run 'sodo [url]' to download video as MP3
echo     - If install fails due to permissions, run with 'sudow install.bat' (run 'tom install sudow' to get sudow)
echo.

if "%1" neq "-y" if "%1" neq "--yes" (
    set /p "CONFIRM=Proceed with installation? [Y/n]: "
    if /i "!CONFIRM!"=="n" (
        echo [!] Installation cancelled.
        exit /b 0
    )
)

echo.
echo [1/2] Checking Python environment...
where pip >nul 2>nul
if %ERRORLEVEL% neq 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        where python >nul 2>nul
        if %ERRORLEVEL% neq 0 (
            echo [ERROR] 'pip' or 'python' was not found in PATH. Please install Python from https://python.org
            exit /b 1
        )
    )
)
echo       Python environment detected.

echo.
echo [2/2] Installing sodo package...
where pip >nul 2>nul
if %ERRORLEVEL% equ 0 (
    pip install -e .
) else (
    py -m pip install -e .
)
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Installation failed. If this is a permission issue, run with 'sudow install.bat' (or install sudow via 'tom install sudow').
    exit /b 1
)

echo.
echo ======================================================================
echo   [+] Successfully installed sodo!
echo   Try running: sodo --help
echo ======================================================================
echo.
