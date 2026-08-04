@echo off
REM AAC Assistant uv-based dependency installer (Windows).
REM
REM Default: core dependencies + frontend build.
REM Optional: install_dependencies.bat voice

setlocal
cd /d "%~dp0"

echo ===================================
echo AAC Assistant - Install Dependencies
echo ===================================

where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv is not installed or not on PATH.
    echo Install it with one of these commands, then rerun this script:
    echo.
    echo   winget install --id=astral-sh.uv -e
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    exit /b 1
)

set "UV_ARGS="
set "INSTALL_ARGS=--skip-sync"
if /I "%~1"=="voice" (
    set "UV_ARGS=--extra voice"
    set "INSTALL_ARGS=--voice --skip-sync"
    echo Voice extra selected: faster-whisper will be installed.
) else (
    echo Core install selected. Voice support can be added later with:
    echo   install_dependencies.bat voice
    echo or:
    echo   uv sync --extra voice
)

echo Syncing Python dependencies with uv...
call uv sync %UV_ARGS%
if errorlevel 1 (
    echo ERROR: uv sync failed.
    exit /b 1
)

echo Preparing .env and the stable JWT secret...
call uv run --no-sync python scripts\install_dependencies.py %INSTALL_ARGS%
if errorlevel 1 (
    echo ERROR: installation preparation failed.
    exit /b 1
)

echo.
echo AAC Assistant is ready. Run start.bat to launch on port 8086.
exit /b 0
