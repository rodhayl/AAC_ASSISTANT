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

set "UV_CMD="
call :resolve_uv
if not defined UV_CMD (
    echo uv is not installed or not on PATH.
    echo Attempting automatic installation...
    call :bootstrap_uv
    call :resolve_uv
)
if not defined UV_CMD (
    echo ERROR: uv could not be installed automatically.
    echo Install it manually, then rerun this script:
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
call "%UV_CMD%" sync %UV_ARGS%
if errorlevel 1 (
    echo ERROR: uv sync failed.
    exit /b 1
)

echo Preparing .env and the stable JWT secret...
call "%UV_CMD%" run --no-sync python scripts\install_dependencies.py %INSTALL_ARGS%
if errorlevel 1 (
    echo ERROR: installation preparation failed.
    exit /b 1
)

echo.
echo AAC Assistant is ready. Run start.bat to launch on port 8086.
exit /b 0

:resolve_uv
where uv >nul 2>&1
if not errorlevel 1 (
    set "UV_CMD=uv"
    goto :eof
)
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
    goto :eof
)
if exist "%LOCALAPPDATA%\Programs\uv\uv.exe" (
    set "UV_CMD=%LOCALAPPDATA%\Programs\uv\uv.exe"
    goto :eof
)
goto :eof

:bootstrap_uv
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id=astral-sh.uv -e --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 goto :eof
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
goto :eof
