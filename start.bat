@echo off
REM AAC Assistant Startup Script (Windows)
REM This script starts both the backend API and frontend development server

setlocal
cd /d "%~dp0"

echo ===================================
echo AAC Assistant - Starting Application
echo ===================================

REM Install/setup dependencies via shared script
call install_dependencies.bat
if errorlevel 1 (
    echo Error: Dependency setup failed.
    pause
    exit /b 1
)

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Error: Virtual environment is missing after dependency setup.
    pause
    exit /b 1
)

REM Create data directory if it doesn't exist
if not exist "data" mkdir data

REM Initialize database if it doesn't exist
if not exist "data\aac_assistant.db" (
    echo Initializing database...
    call "%PYTHON_EXE%" -c "from src.aac_app.models.database import init_database; init_database()"
)

REM Ensure a bootstrap admin account exists on first run
echo Ensuring bootstrap admin account...
call "%PYTHON_EXE%" scripts\ensure_bootstrap_admin.py
if errorlevel 1 (
    echo.
    echo Bootstrap admin setup failed.
    pause
    exit /b 1
)

REM Validate database before starting
echo Validating database...
call "%PYTHON_EXE%" scripts\validate_database.py
if errorlevel 1 (
    echo.
    echo Database validation failed! Please fix the errors above.
    pause
    exit /b 1
)

if /I "%~1"=="--prepare-only" (
    echo Preparation completed successfully. Exiting due to --prepare-only.
    exit /b 0
)

REM Start backend in a new window
echo Starting backend API server on port 8086...
start "AAC Backend" cmd /k ""%PYTHON_EXE%" -m uvicorn src.api.main:app --host 0.0.0.0 --port 8086"

REM Wait for backend port to become available (up to ~30s)
set WAIT_COUNT=0
:wait_backend
for /f "tokens=*" %%K in ('powershell -Command "($x=Test-NetConnection -ComputerName localhost -Port 8086 -WarningAction SilentlyContinue).TcpTestSucceeded"') do set PORT_READY=%%K
if "%PORT_READY%"=="True" (
    echo Backend is up.
) else (
    set /a WAIT_COUNT+=1
    if %WAIT_COUNT% GEQ 60 (
        echo Error: Backend did not start within 30 seconds.
        goto start_frontend
    )
    timeout /t 1 /nobreak >nul
    goto wait_backend
)

:start_frontend
REM Start frontend development server in a new window
echo Starting frontend development server on port 5176...
cd src\frontend

start "AAC Frontend" cmd /k "npm run dev"

cd ..\..

echo.
echo ===================================
echo Application started successfully!
echo ===================================
echo Backend API: http://localhost:8086
echo Frontend: http://localhost:5176
echo API Docs: http://localhost:8086/docs
echo.
echo Close the terminal windows to stop the servers
echo ===================================

