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

REM Ensure local Whisper (voice) dependencies are present (silent if already installed)
call "%PYTHON_EXE%" scripts\ensure_whisper_deps.py
if exist "logs\whisper_dep_install.log" (
    echo See logs\whisper_dep_install.log for voice dependency status.
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
if not exist "env.properties" (
    echo Creating local env.properties from template...
    if exist "env.properties.example" (
        copy /Y "env.properties.example" "env.properties" >nul
    ) else (
        type nul > "env.properties"
    )
)

REM Ensure bootstrap admin settings exist
findstr /B /C:"AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=" "env.properties" >nul
if errorlevel 1 (
    echo.
    >> "env.properties" echo # Bootstrap admin for first run
    >> "env.properties" echo AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=true
    >> "env.properties" echo AAC_BOOTSTRAP_ADMIN_USERNAME=admin1
    >> "env.properties" echo AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123
)

REM Ensure JWT secret is present and not placeholder
set "NEED_JWT=0"
findstr /B /C:"JWT_SECRET_KEY=" "env.properties" >nul
if errorlevel 1 set "NEED_JWT=1"
findstr /C:"JWT_SECRET_KEY=CHANGE_ME_TO_A_SECURE_RANDOM_STRING" "env.properties" >nul
if not errorlevel 1 set "NEED_JWT=1"

if "!NEED_JWT!"=="1" (
    echo Generating secure JWT secret key...
    for /f "tokens=*" %%a in ('"%PYTHON_EXE%" scripts\generate_jwt_secret.py') do set "JWT_SECRET=%%a"
    if "!JWT_SECRET!"=="" (
        echo Error: Failed to generate JWT secret key.
        exit /b 1
    )
    echo.>> "env.properties"
    >> "env.properties" echo # Security (generated locally)
    >> "env.properties" echo JWT_SECRET_KEY=!JWT_SECRET!
)

echo Dependencies are ready.
exit /b 0
