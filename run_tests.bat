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

echo Syncing development tools with uv...
call uv sync --group dev
if errorlevel 1 (
    echo Development dependency sync failed.
    exit /b 1
)

echo Running backend tests...
call uv run pytest -q tests
if errorlevel 1 (
    echo Backend tests failed.
    exit /b 1
)

echo Running Ruff...
call uv run ruff check src tests scripts
if errorlevel 1 (
    echo Backend lint failed.
    exit /b 1
)

call uv run python scripts/audit_codebase.py
if errorlevel 1 (
    echo Internal import audit failed.
    exit /b 1
)

echo Verifying frontend lockfile and dependency graph...
call npm --prefix src/frontend ci --dry-run
if errorlevel 1 (
    echo Frontend package-lock.json is out of sync.
    exit /b 1
)

echo Running frontend typecheck...
call npm --prefix src/frontend run typecheck
if errorlevel 1 (
    echo Frontend typecheck failed.
    exit /b 1
)

echo Running frontend lint...
call npm --prefix src/frontend run lint -- --max-warnings=0
if errorlevel 1 (
    echo Frontend lint failed.
    exit /b 1
)

echo Running frontend tests...
call npm --prefix src/frontend test -- --run
if errorlevel 1 (
    echo Frontend tests failed.
    exit /b 1
)

echo Running frontend i18n audit...
call npm --prefix src/frontend run i18n:audit
if errorlevel 1 (
    echo Frontend i18n audit failed.
    exit /b 1
)

echo Running frontend production build...
call npm --prefix src/frontend run build
if errorlevel 1 (
    echo Frontend production build failed.
    exit /b 1
)

echo Running frontend E2E build...
call npm --prefix src/frontend run build:e2e
if errorlevel 1 (
    echo Frontend production build failed.
    exit /b 1
)

echo Verifying frontend bundle size...
call npm --prefix src/frontend run check:bundle-size
if errorlevel 1 (
    echo Frontend bundle size budget exceeded.
    exit /b 1
)

echo All tests and quality checks passed.
exit /b 0
