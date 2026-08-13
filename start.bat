@echo off
REM AAC Assistant production launcher.
REM Production serves the built SPA, API, uploads, and docs from one uvicorn process.
REM Pass --dev explicitly to run uvicorn plus the Vite development server.

setlocal
cd /d "%~dp0"

set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
if exist "%PYTHON_CMD%" goto run

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
    echo Run install_dependencies.bat after installing uv manually.
    exit /b 1
)

:run
echo Starting AAC Assistant...
if exist "%PYTHON_CMD%" (
    call "%PYTHON_CMD%" -m scripts.start_server %*
) else (
    call "%UV_CMD%" run python -m scripts.start_server %*
)
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
