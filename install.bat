@echo off
REM install.bat — install llamaUI on Windows
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo === llamaUI installer ===

echo [1/2] Installing...
pip install -e .

echo [2/2] Done. Launch with: llamaui
pause
