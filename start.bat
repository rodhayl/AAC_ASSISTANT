@echo off
REM AAC Assistant production launcher.
REM Production serves the built SPA, API, uploads, and docs from one uvicorn process.
REM Pass --dev explicitly to run uvicorn plus the Vite development server.

setlocal
cd /d "%~dp0"

set "UV_CMD="
call :resolve_uv
if not defined UV_CMD (
    echo uv is not installed or not on PATH.
    echo Attempting automatic installation...
    call :bootstrap_uv
    call :resolve_uv
)
if not defined UV_CMD (
    if exist "%~dp0.venv\Scripts\python.exe" (
        echo uv is unavailable; using the existing Python environment.
        call "%~dp0.venv\Scripts\python.exe" -m scripts.ensure_voice_runtime
        if errorlevel 1 (
            echo ERROR: voice runtime preparation failed.
            exit /b 1
        )
        call "%~dp0.venv\Scripts\python.exe" -m scripts.start_server %*
        if errorlevel 1 exit /b 1
        exit /b 0
    )
    echo ERROR: uv could not be installed automatically.
    echo Install uv manually or install it with winget, then run start.bat again.
    exit /b 1
)

set "UV_SYNC_ARGS=--no-dev --extra voice --extra tts"
call :check_dev_dependencies
if not errorlevel 1 (
    set "UV_SYNC_ARGS=--group dev --extra voice --extra tts"
) else if not defined CI (
    choice /C YN /N /M "Development dependencies are missing. Install them? [Y/N]"
    if not errorlevel 2 set "UV_SYNC_ARGS=--group dev --extra voice --extra tts"
)

echo Creating or updating the Python environment and installing dependencies...
call "%UV_CMD%" sync %UV_SYNC_ARGS%
if errorlevel 1 (
    echo ERROR: uv sync failed.
    exit /b 1
)

echo Preparing voice dependencies and Kokoro model...
call "%UV_CMD%" run --no-sync python -m scripts.ensure_voice_runtime
if errorlevel 1 (
    echo ERROR: voice runtime preparation failed.
    exit /b 1
)

echo Starting AAC Assistant...
call "%UV_CMD%" run --no-sync python -m scripts.start_server %*
exit /b %errorlevel%

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

:check_dev_dependencies
call "%UV_CMD%" run --no-sync python -m scripts.check_dev_dependencies >nul 2>&1
exit /b %errorlevel%

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
