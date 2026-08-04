@echo off
REM AAC Assistant dependency installer (Windows)

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================
echo AAC Assistant - Install Dependencies
echo ===================================

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM Check if Node.js is available
node --version >nul 2>&1
if errorlevel 1 (
    echo Error: Node.js is not installed or not in PATH
    exit /b 1
)

REM Create virtual environment if it does not exist
if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        exit /b 1
    )
)

set "PYTHON_EXE=.venv\Scripts\python.exe"

echo Installing Python dependencies...
call "%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install Python dependencies
    exit /b 1
)

REM Install frontend dependencies if missing
if not exist "src\frontend\node_modules" (
    echo Installing frontend dependencies...
    pushd src\frontend
    call npm install
    if errorlevel 1 (
        popd
        echo Error: Failed to install frontend dependencies
        exit /b 1
    )
    popd
)

REM Ensure local configuration exists
if not exist ".env" (
    echo Creating local .env from template...
    if exist "env.properties" (
        copy /Y "env.properties" ".env" >nul
    ) else if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
    ) else if exist "env.properties.example" (
        copy /Y "env.properties.example" ".env" >nul
    ) else (
        type nul > ".env"
    )
)

REM Ensure bootstrap admin settings exist
findstr /B /C:"AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=" ".env" >nul
if errorlevel 1 (
    echo.
    >> ".env" echo # Bootstrap admin for first run
    >> ".env" echo AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=true
    >> ".env" echo AAC_BOOTSTRAP_ADMIN_USERNAME=admin1
    >> ".env" echo AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123
)

REM Ensure JWT_SECRET_KEY is present exactly once, replacing any placeholder.
echo Ensuring secure JWT secret key...
call "%PYTHON_EXE%" scripts\generate_jwt_secret.py --env-file ".env" >nul
if errorlevel 1 (
    echo Error: Failed to generate secure JWT secret key.
    exit /b 1
)

echo Dependencies are ready.
exit /b 0
