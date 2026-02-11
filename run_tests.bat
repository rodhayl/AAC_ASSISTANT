@echo off
REM AAC Assistant test runner (Windows)

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "MISSING_DEPS=0"

if not exist ".venv\Scripts\python.exe" (
    set "MISSING_DEPS=1"
)

if not exist "src\frontend\node_modules" (
    set "MISSING_DEPS=1"
)

if "%MISSING_DEPS%"=="1" (
    echo Dependencies/environment are missing.
    echo Required:
    echo   - .venv\Scripts\python.exe
    echo   - src\frontend\node_modules
    echo.
    if not "%~1"=="" (
        set "INSTALL_DEPS=%~1"
    ) else (
        set /p INSTALL_DEPS="Dependencies are missing. Would you like to install them now? (Y/N) "
    )

    set "INSTALL_DEPS=!INSTALL_DEPS: =!"
    if /I "!INSTALL_DEPS!"=="Y" (
        call install_dependencies.bat
        if errorlevel 1 (
            echo Error: Failed to install dependencies.
            exit /b 1
        )
    ) else if /I "!INSTALL_DEPS!"=="YES" (
        call install_dependencies.bat
        if errorlevel 1 (
            echo Error: Failed to install dependencies.
            exit /b 1
        )
    ) else (
        echo Exiting without running tests.
        exit /b 1
    )
)

echo ===================================
echo AAC Assistant - Running Tests
echo ===================================

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Error: Python environment is still missing.
    exit /b 1
)

echo Running backend tests...
call "%PYTHON_EXE%" -m pytest -q tests
if errorlevel 1 (
    echo Backend tests failed.
    exit /b 1
)

echo Running frontend tests...
call npm --prefix src/frontend test -- --run
if errorlevel 1 (
    echo Frontend tests failed.
    exit /b 1
)

echo All tests passed.
exit /b 0
