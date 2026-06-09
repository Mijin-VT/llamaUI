@echo off
REM llamaUI — cross-platform launcher (Windows)
REM Usage: llamaui.bat
setlocal

cd /d "%~dp0"

where python >nul 2>&1 || (
    echo ERROR: python is required but not found.
    echo   Install it from https://www.python.org/downloads/
    exit /b 1
)

python -c "import PySide6" >nul 2>&1 || (
    echo PySide6 not found — installing...
    pip install PySide6
)

python -m qt_app %*
