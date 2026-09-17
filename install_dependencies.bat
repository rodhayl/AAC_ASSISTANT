@echo off
REM AAC Assistant uv-based dependency installer (Windows).
REM
REM Default: core dependencies + frontend build.
REM Optional: install_dependencies.bat voice

setlocal
cd /d "%~dp0"

REM Pin the virtual environment to the project-local (gitignored) .venv and
REM keep uv's cache in the user profile, never inside the workspace.
set "UV_PROJECT_ENVIRONMENT=%~dp0.venv"

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

REM kokoro-onnx only supports Python 3.13; pin the environment so a system
REM Python 3.14 checkout does not silently drop the neural voice stack.
set "VOICE_PYTHON_VERSION=3.13"
if not exist ".venv\Scripts\python.exe" (
    REM Windows Smart App Control blocks uv's generated venv launcher
    REM (os error 4551) because it is written at runtime. Pre-seed the
    REM environment with the standard library venv module, which copies the
    REM real signed interpreter, then let uv fill it. Harmless elsewhere.
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
echo Syncing Python %VOICE_PYTHON_VERSION% dependencies with uv...
call "%UV_CMD%" sync --frozen --python %VOICE_PYTHON_VERSION% %UV_ARGS%
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
REM winget installs uv into a versioned package directory that the current
REM shell's PATH does not contain until a new terminal is opened.
for /f "delims=" %%D in ('dir /b /ad "%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*" 2^>nul') do (
    if exist "%LOCALAPPDATA%\Microsoft\WinGet\Packages\%%D\uv.exe" (
        set "UV_CMD=%LOCALAPPDATA%\Microsoft\WinGet\Packages\%%D\uv.exe"
        goto :eof
    )
)
goto :eof

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
