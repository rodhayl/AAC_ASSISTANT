@echo off
REM AAC Assistant production launcher.
REM Production serves the built SPA, API, uploads, and docs from one uvicorn process.
REM Pass --dev explicitly to run uvicorn plus the Vite development server.

setlocal
cd /d "%~dp0"

REM Keep uv state out of the source tree: the virtual environment is pinned to
REM the project-local (gitignored) .venv directory, sync never rewrites the
REM committed uv.lock (--frozen), and uv's package cache stays in the user
REM profile instead of the workspace.
set "UV_PROJECT_ENVIRONMENT=%~dp0.venv"

REM kokoro-onnx currently supports Python 3.13, but its package metadata excludes
REM Python 3.14. Pin the launcher to the compatible interpreter (same as
REM start.sh) so the local neural voice is installed instead of silently
REM falling back to browser TTS on a 3.14-resolving checkout.
set "VOICE_PYTHON_VERSION=3.13"

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
        REM Offline fallback: the existing environment must already be on the
        REM interpreter that supports the voice stack.
        "%~dp0.venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 13))"
        if errorlevel 1 (
            echo ERROR: the existing .venv is not Python %VOICE_PYTHON_VERSION%, which is required for Kokoro.
            echo Install uv or recreate the environment with: uv sync --python %VOICE_PYTHON_VERSION% --extra tts
            exit /b 1
        )
        echo uv is unavailable; using the existing Python %VOICE_PYTHON_VERSION% environment.
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

if not exist ".venv\Scripts\python.exe" (
    REM Windows Smart App Control blocks uv's generated venv launcher
    REM (os error 4551) because it is written at runtime. Pre-seed the
    REM environment with the standard library venv module, which copies the
    REM real signed interpreter, then let uv fill it. Harmless elsewhere.
    REM This must run before any `uv run`: an unpinned run would create a
    REM venv that SAC then blocks.
    call "%UV_CMD%" python install %VOICE_PYTHON_VERSION% >nul 2>&1
    set "BASE_PY="
    for /f "delims=" %%D in ('dir /b /ad "%USERPROFILE%\AppData\Roaming\uv\python\cpython-%VOICE_PYTHON_VERSION%*" 2^>nul') do (
        if not defined BASE_PY if exist "%USERPROFILE%\AppData\Roaming\uv\python\%%D\python.exe" set "BASE_PY=%USERPROFILE%\AppData\Roaming\uv\python\%%D\python.exe"
    )
)

REM Parsed separately on purpose: %BASE_PY% is only readable here, after the
REM block above has executed (inside one block, %VAR% expands at parse time).
if not exist ".venv\Scripts\python.exe" if defined BASE_PY (
    echo Preparing the Python %VOICE_PYTHON_VERSION% virtual environment...
    "%BASE_PY%" -m venv .venv
)

set "UV_SYNC_ARGS=--no-dev --extra voice --extra tts"
call :check_dev_dependencies
if not errorlevel 1 (
    set "UV_SYNC_ARGS=--group dev --extra voice --extra tts"
) else if not defined CI (
    choice /C YN /N /M "Development dependencies are missing. Install them? [Y/N]"
    if not errorlevel 2 set "UV_SYNC_ARGS=--group dev --extra voice --extra tts"
)

echo Creating or updating the Python %VOICE_PYTHON_VERSION% environment in .venv and installing dependencies...
call "%UV_CMD%" sync --frozen --python %VOICE_PYTHON_VERSION% %UV_SYNC_ARGS%
if errorlevel 1 (
    echo ERROR: uv sync failed.
    exit /b 1
)

echo Preparing voice dependencies and Kokoro model...
call "%UV_CMD%" run --python %VOICE_PYTHON_VERSION% --no-sync python -m scripts.ensure_voice_runtime
if errorlevel 1 (
    echo ERROR: voice runtime preparation failed.
    exit /b 1
)

echo Starting AAC Assistant...
call "%UV_CMD%" run --python %VOICE_PYTHON_VERSION% --no-sync python -m scripts.start_server %*
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
REM winget installs uv into a versioned package directory that the current
REM shell's PATH does not contain until a new terminal is opened.
for /f "delims=" %%D in ('dir /b /ad "%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*" 2^>nul') do (
    if exist "%LOCALAPPDATA%\Microsoft\WinGet\Packages\%%D\uv.exe" (
        set "UV_CMD=%LOCALAPPDATA%\Microsoft\WinGet\Packages\%%D\uv.exe"
        goto :eof
    )
)
goto :eof

:check_dev_dependencies
REM Pin the interpreter here too: an unpinned `uv run` would create the
REM project venv with the system Python (e.g. 3.14) before the pinned sync
REM below can place the required 3.13 environment (parity with start.sh).
call "%UV_CMD%" run --python %VOICE_PYTHON_VERSION% --no-sync python -m scripts.check_dev_dependencies >nul 2>&1
exit /b %errorlevel%

:bootstrap_uv
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id=astral-sh.uv -e --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 goto :bootstrap_done
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"

:bootstrap_done
REM A freshly installed uv is not on this shell's PATH yet. Locate it and
REM prepend its directory so the rest of this script and its child processes
REM can use it without opening a new terminal.
call :resolve_uv
if not defined UV_CMD goto :eof
for %%F in ("%UV_CMD%") do set "PATH=%%~dpF;%PATH%"
goto :eof
