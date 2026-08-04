@echo off
REM AAC Assistant production launcher.
REM Production serves the built SPA, API, uploads, and docs from one uvicorn process.
REM Pass --dev explicitly to run uvicorn plus the Vite development server.

setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv is not installed or not on PATH.
    echo Install uv, then run install_dependencies.bat before starting AAC Assistant.
    exit /b 1
)

echo Starting AAC Assistant...
call uv run python -m scripts.start_server %*
exit /b %errorlevel%

