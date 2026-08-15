@echo off
cd /d "%~dp0"
echo [*] Installing sodo...
powershell -NoProfile -Command "Set-Location -LiteralPath '%~dp0'; pip install -e ."
