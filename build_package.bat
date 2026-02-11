@echo off
REM ============================================================================
REM AAC Assistant - Build Package Script for Windows
REM ============================================================================
REM This script creates a distributable package for the AAC Assistant application
REM that can be installed and used on other Windows machines.
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================
echo AAC Assistant - Build Package
echo ===================================
echo.

REM Configuration
set "PACKAGE_NAME=AAC_Assistant_Package"
set "OUTPUT_DIR=dist\%PACKAGE_NAME%"
set "VERSION=2.0.0"

REM Prompt for build type
if not "%BUILD_TYPE%"=="" (
    echo Using pre-set build type: %BUILD_TYPE%
) else (
    set /p BUILD_TYPE="Build type (production/testing/exe)? [production]: "
    if "%BUILD_TYPE%"=="" set BUILD_TYPE=production
)
echo Building for: %BUILD_TYPE%


REM Check prerequisites
echo [1/7] Checking prerequisites...

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH
    exit /b 1
)

echo       Python and Node.js found.



REM Clean up persistent processes from previous runs
echo [1.5/7] Stopping existing processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
REM NOTE: Avoid killing node.exe globally; it may be used by developer tooling (e.g., IDE/DevTools integrations).
REM taskkill /F /IM node.exe >nul 2>&1
REM Try to kill port 8086 specifically just in case
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8086') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul

REM Clean previous build
echo [2/7] Cleaning previous build...
if exist "dist\%PACKAGE_NAME%" (
    rmdir /s /q "dist\%PACKAGE_NAME%" >nul 2>&1
    if exist "dist\%PACKAGE_NAME%" (
        echo WARNING: Failed to fully remove output directory. Retrying...
        timeout /t 2 /nobreak >nul
        rmdir /s /q "dist\%PACKAGE_NAME%"
    )
)
mkdir "dist\%PACKAGE_NAME%"

REM Build frontend production bundle
echo [3/7] Building frontend production bundle...
cd src\frontend
call npm install >nul 2>&1
call npm run build
if errorlevel 1 (
    echo ERROR: Frontend build failed
    cd ..\..
    exit /b 1
)
cd ..\..
echo       Frontend built successfully.
if /i "%BUILD_TYPE%"=="exe" goto build_exe
goto build_standard

:build_exe
echo [4/7] Building One-Folder Executable Package...
echo       This may take several minutes...

python -m PyInstaller AAC_Assistant.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    exit /b 1
)

echo [5/7] Verifying build output...
if not exist "dist\AAC_Assistant\AAC_Assistant.exe" (
    echo ERROR: Build output not found at dist\AAC_Assistant\
    exit /b 1
)

echo [6/7] Copying additional data...
REM Copy env.properties if it doesn't exist in output
if not exist "dist\AAC_Assistant\env.properties" (
    copy /Y "env.properties.example" "dist\AAC_Assistant\env.properties" >nul 2>&1
)

REM Ensure data directory exists with symbols
if not exist "dist\AAC_Assistant\data" mkdir "dist\AAC_Assistant\data"
xcopy /E /I /Y "data\symbols" "dist\AAC_Assistant\data\symbols" >nul 2>&1
copy /Y "data\*.json" "dist\AAC_Assistant\data\" >nul 2>&1

REM Create logs and uploads directories
if not exist "dist\AAC_Assistant\logs" mkdir "dist\AAC_Assistant\logs"
if not exist "dist\AAC_Assistant\uploads" mkdir "dist\AAC_Assistant\uploads"

echo [7/7] Creating Windows Installer...
REM Check if Inno Setup is available
where iscc >nul 2>&1
if errorlevel 1 (
    echo WARNING: Inno Setup Compiler (iscc) not found in PATH.
    echo          Skipping installer creation.
    echo          Install Inno Setup from: https://jrsoftware.org/isinfo.php
    echo.
    echo ===================================
    echo Build Complete (Folder Package)
    echo ===================================
    echo.
    echo Package created at: dist\AAC_Assistant\
    echo Contains: AAC_Assistant.exe and all dependencies
    echo.
    echo To distribute:
    echo   1. Zip the 'dist\AAC_Assistant' folder
    echo   2. Or install Inno Setup to create a proper installer
    echo.
) else (
    echo       Building installer with Inno Setup...
    iscc installer.iss
    if errorlevel 1 (
        echo WARNING: Installer creation failed. Folder package is still available.
    ) else (
        echo.
        echo ===================================
        echo Build Complete (EXE + Installer)
        echo ===================================
        echo.
        echo Folder package: dist\AAC_Assistant\
        echo Installer: dist\AAC_Assistant_Setup_%VERSION%.exe
        echo.
        echo To distribute:
        echo   Share the installer .exe file with users.
        echo.
    )
)
exit /b 0

:build_standard

REM Copy source files
echo [4/7] Copying application files...

REM Core directories
xcopy /E /I /Y "src\aac_app" "%OUTPUT_DIR%\src\aac_app" >nul
xcopy /E /I /Y "src\api" "%OUTPUT_DIR%\src\api" >nul
copy /Y "src\__init__.py" "%OUTPUT_DIR%\src\" >nul
copy /Y "src\config.py" "%OUTPUT_DIR%\src\" >nul

REM Built frontend (dist folder from vite build)
xcopy /E /I /Y "src\frontend\dist" "%OUTPUT_DIR%\frontend" >nul

REM Scripts directory (utilities)
xcopy /E /I /Y "scripts" "%OUTPUT_DIR%\scripts" >nul

REM Configuration and requirements
copy /Y "requirements.txt" "%OUTPUT_DIR%\" >nul
copy /Y "pytest.ini" "%OUTPUT_DIR%\" >nul
if exist "env.properties.example" copy /Y "env.properties.example" "%OUTPUT_DIR%\" >nul

REM Create data directory placeholder
mkdir "%OUTPUT_DIR%\data" 2>nul

REM Copy existing data if requested (testing mode)
if /i "%BUILD_TYPE%"=="testing" (
    echo [4.5/7] Copying current data...
    xcopy /E /I /Y "data" "%OUTPUT_DIR%\data" >nul
    if errorlevel 1 (
        echo WARNING: Failed to prepare test database. Continuing...
    )
)


REM Launcher
copy /Y "launcher.pyw" "%OUTPUT_DIR%\" >nul

echo       Files copied successfully.

REM Create install script
REM Create install script (Enhanced)
echo [5/7] Creating install script...
> "%OUTPUT_DIR%\install.bat" echo @echo off
>> "%OUTPUT_DIR%\install.bat" echo setlocal enabledelayedexpansion
>> "%OUTPUT_DIR%\install.bat" echo REM AAC Assistant - Installation Script
>> "%OUTPUT_DIR%\install.bat" echo REM This script creates a local environment and installs dependencies
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo echo ===================================
>> "%OUTPUT_DIR%\install.bat" echo echo AAC Assistant - Installation
>> "%OUTPUT_DIR%\install.bat" echo echo ===================================
>> "%OUTPUT_DIR%\install.bat" echo echo.
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo REM Check Python
>> "%OUTPUT_DIR%\install.bat" echo python --version ^>nul 2^>^&1
>> "%OUTPUT_DIR%\install.bat" echo ^if errorlevel 1 ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo ERROR: Python is not installed or not in PATH.
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo Python 3.8+ is required to install this application.
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     set /p "OPEN_PY=Would you like to open the Python download page? (Y/N): "
>> "%OUTPUT_DIR%\install.bat" echo     ^if /i "^!OPEN_PY^!"=="Y" start https://www.python.org/downloads/
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo Please install Python and try again.
>> "%OUTPUT_DIR%\install.bat" echo     pause
>> "%OUTPUT_DIR%\install.bat" echo     exit /b 1
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo REM Check Node.js ^(Optional^)
>> "%OUTPUT_DIR%\install.bat" echo node --version ^>nul 2^>^&1
>> "%OUTPUT_DIR%\install.bat" echo ^if errorlevel 1 ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo WARNING: Node.js is not installed.
>> "%OUTPUT_DIR%\install.bat" echo     echo This is usually fine for running the application, but development tools may not work.
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo echo [1/2] Creating local virtual environment...
>> "%OUTPUT_DIR%\install.bat" echo ^if not exist ".venv" ^(
>> "%OUTPUT_DIR%\install.bat" echo     python -m venv .venv
>> "%OUTPUT_DIR%\install.bat" echo     ^if errorlevel 1 ^(
>> "%OUTPUT_DIR%\install.bat" echo         echo ERROR: Failed to create virtual environment.
>> "%OUTPUT_DIR%\install.bat" echo         pause
>> "%OUTPUT_DIR%\install.bat" echo         exit /b 1
>> "%OUTPUT_DIR%\install.bat" echo     ^)
>> "%OUTPUT_DIR%\install.bat" echo     echo     Virtual environment created.
>> "%OUTPUT_DIR%\install.bat" echo ^) else ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo     Virtual environment already exists.
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo echo [2/2] Installing dependencies into local environment...
>> "%OUTPUT_DIR%\install.bat" echo echo       This may take a few minutes...
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo .venv\Scripts\python -m pip install --upgrade pip
>> "%OUTPUT_DIR%\install.bat" echo .venv\Scripts\python -m pip install -r requirements.txt
>> "%OUTPUT_DIR%\install.bat" echo set "PIP_INSTALL_EXIT=%%ERRORLEVEL%%"
>> "%OUTPUT_DIR%\install.bat" echo .venv\Scripts\python -m pip check
>> "%OUTPUT_DIR%\install.bat" echo ^if errorlevel 1 ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo ===============================================================================
>> "%OUTPUT_DIR%\install.bat" echo     echo ERROR: Failed to install Python dependencies.
>> "%OUTPUT_DIR%\install.bat" echo     echo ===============================================================================
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo Common causes:
>> "%OUTPUT_DIR%\install.bat" echo     echo 1. Missing "Microsoft C++ Build Tools" ^^(required for webrtcvad^^)
>> "%OUTPUT_DIR%\install.bat" echo     echo 2. Network connectivity issues
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo If you see an error about "Microsoft Visual C++ 14.0 or greater",
>> "%OUTPUT_DIR%\install.bat" echo     echo you MUST install the C++ Build Tools.
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     set /p "OPEN_BUILD=Would you like to open the C++ Build Tools download page? (Y/N): "
>> "%OUTPUT_DIR%\install.bat" echo     ^if /i "^!OPEN_BUILD^!"=="Y" start https://visualstudio.microsoft.com/visual-cpp-build-tools/
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo After installing Build Tools, run this script again.
>> "%OUTPUT_DIR%\install.bat" echo     pause
>> "%OUTPUT_DIR%\install.bat" echo     exit /b 1
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo ^if not "^!PIP_INSTALL_EXIT^!"=="0" ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo WARNING: pip returned exit code ^^!PIP_INSTALL_EXIT^^! but pip check passed; continuing.
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo REM Generate Secure JWT Key if missing
>> "%OUTPUT_DIR%\install.bat" echo ^if not exist "env.properties" ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo Creating basic configuration...
>> "%OUTPUT_DIR%\install.bat" echo     copy env.properties.example env.properties ^>nul 2^>^&1
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo REM Ensure bootstrap admin settings exist
>> "%OUTPUT_DIR%\install.bat" echo findstr /C:"AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN" env.properties ^>nul
>> "%OUTPUT_DIR%\install.bat" echo ^if errorlevel 1 ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo.
>> "%OUTPUT_DIR%\install.bat" echo     echo # Bootstrap admin for first run^>^> env.properties
>> "%OUTPUT_DIR%\install.bat" echo     echo AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=true^>^> env.properties
>> "%OUTPUT_DIR%\install.bat" echo     echo AAC_BOOTSTRAP_ADMIN_USERNAME=admin1^>^> env.properties
>> "%OUTPUT_DIR%\install.bat" echo     echo AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123^>^> env.properties
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo echo Checking security configuration...
>> "%OUTPUT_DIR%\install.bat" echo set "NEED_JWT=0"
>> "%OUTPUT_DIR%\install.bat" echo findstr /C:"JWT_SECRET_KEY" env.properties ^>nul
>> "%OUTPUT_DIR%\install.bat" echo ^if errorlevel 1 set "NEED_JWT=1"
>> "%OUTPUT_DIR%\install.bat" echo findstr /C:"JWT_SECRET_KEY=CHANGE_ME_TO_A_SECURE_RANDOM_STRING" env.properties ^>nul
>> "%OUTPUT_DIR%\install.bat" echo ^if not errorlevel 1 set "NEED_JWT=1"
>> "%OUTPUT_DIR%\install.bat" echo ^if "^!NEED_JWT^!"=="1" ^(
>> "%OUTPUT_DIR%\install.bat" echo     echo Generating secure JWT secret key...
>> "%OUTPUT_DIR%\install.bat" echo     for /f "tokens=*" %%%%a in ^('.venv\Scripts\python scripts\generate_jwt_secret.py'^) do set "SECRET_KEY=%%%%a"
>> "%OUTPUT_DIR%\install.bat" echo     ^if "^!SECRET_KEY^!"=="" ^(
>> "%OUTPUT_DIR%\install.bat" echo         echo ERROR: Failed to generate JWT secret key.
>> "%OUTPUT_DIR%\install.bat" echo         pause
>> "%OUTPUT_DIR%\install.bat" echo         exit /b 1
>> "%OUTPUT_DIR%\install.bat" echo     ^)
>> "%OUTPUT_DIR%\install.bat" echo     echo.^>^> env.properties
>> "%OUTPUT_DIR%\install.bat" echo     echo # Security^>^> env.properties
>> "%OUTPUT_DIR%\install.bat" echo     echo JWT_SECRET_KEY=^^!SECRET_KEY^^!^>^> env.properties
>> "%OUTPUT_DIR%\install.bat" echo     echo Key generated successfully.
>> "%OUTPUT_DIR%\install.bat" echo ^)
>> "%OUTPUT_DIR%\install.bat" echo.
>> "%OUTPUT_DIR%\install.bat" echo echo.
>> "%OUTPUT_DIR%\install.bat" echo echo ===================================
>> "%OUTPUT_DIR%\install.bat" echo echo Installation Complete!
>> "%OUTPUT_DIR%\install.bat" echo echo ===================================
>> "%OUTPUT_DIR%\install.bat" echo echo.
>> "%OUTPUT_DIR%\install.bat" echo echo Run 'run.bat' to start the application.
>> "%OUTPUT_DIR%\install.bat" echo echo.
>> "%OUTPUT_DIR%\install.bat" echo pause

REM Create run script
echo [6/7] Creating run script...
> "%OUTPUT_DIR%\run.bat" echo @echo off
>> "%OUTPUT_DIR%\run.bat" echo REM AAC Assistant - Run Script
>> "%OUTPUT_DIR%\run.bat" echo cd /d "%%~dp0"
>> "%OUTPUT_DIR%\run.bat" echo ^if not exist "data" mkdir data
>> "%OUTPUT_DIR%\run.bat" echo.
>> "%OUTPUT_DIR%\run.bat" echo REM Check for virtual environment
>> "%OUTPUT_DIR%\run.bat" echo ^if not exist ".venv\Scripts\python.exe" ^(
>> "%OUTPUT_DIR%\run.bat" echo     echo ERROR: Virtual environment not found.
>> "%OUTPUT_DIR%\run.bat" echo     echo Please run 'install.bat' first.
>> "%OUTPUT_DIR%\run.bat" echo     pause
>> "%OUTPUT_DIR%\run.bat" echo     exit /b 1
>> "%OUTPUT_DIR%\run.bat" echo ^)
>> "%OUTPUT_DIR%\run.bat" echo.
>> "%OUTPUT_DIR%\run.bat" echo echo Killing any existing process on port 8086...
>> "%OUTPUT_DIR%\run.bat" echo for /f "tokens=5" %%%%a in ('netstat -ano ^^^| findstr ":8086"') do taskkill /F /PID %%%%a 2^>nul
>> "%OUTPUT_DIR%\run.bat" echo.
>> "%OUTPUT_DIR%\run.bat" echo echo Ensuring bootstrap admin account...
>> "%OUTPUT_DIR%\run.bat" echo .venv\Scripts\python scripts\ensure_bootstrap_admin.py
>> "%OUTPUT_DIR%\run.bat" echo ^if errorlevel 1 ^(
>> "%OUTPUT_DIR%\run.bat" echo     echo ERROR: Bootstrap admin setup failed.
>> "%OUTPUT_DIR%\run.bat" echo     pause
>> "%OUTPUT_DIR%\run.bat" echo     exit /b 1
>> "%OUTPUT_DIR%\run.bat" echo ^)
>> "%OUTPUT_DIR%\run.bat" echo.
>> "%OUTPUT_DIR%\run.bat" echo echo Starting AAC Assistant...
>> "%OUTPUT_DIR%\run.bat" echo start /B .venv\Scripts\python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8086
>> "%OUTPUT_DIR%\run.bat" echo.
>> "%OUTPUT_DIR%\run.bat" echo echo Waiting for server to start...
>> "%OUTPUT_DIR%\run.bat" echo :wait_loop
>> "%OUTPUT_DIR%\run.bat" echo timeout /t 2 /nobreak ^>nul
>> "%OUTPUT_DIR%\run.bat" echo netstat -ano ^| findstr "8086" ^| findstr "LISTENING" ^>nul
>> "%OUTPUT_DIR%\run.bat" echo ^if errorlevel 1 goto wait_loop
>> "%OUTPUT_DIR%\run.bat" echo.
>> "%OUTPUT_DIR%\run.bat" echo echo Server is ready! Opening in browser...
>> "%OUTPUT_DIR%\run.bat" echo start http://localhost:8086
>> "%OUTPUT_DIR%\run.bat" echo echo.
>> "%OUTPUT_DIR%\run.bat" echo echo ===================================
>> "%OUTPUT_DIR%\run.bat" echo echo AAC Assistant is running!
>> "%OUTPUT_DIR%\run.bat" echo echo ===================================
>> "%OUTPUT_DIR%\run.bat" echo echo Application: http://localhost:8086
>> "%OUTPUT_DIR%\run.bat" echo echo API Docs: http://localhost:8086/docs
>> "%OUTPUT_DIR%\run.bat" echo echo.
>> "%OUTPUT_DIR%\run.bat" echo echo Press any key to stop the server...
>> "%OUTPUT_DIR%\run.bat" echo pause ^>nul
>> "%OUTPUT_DIR%\run.bat" echo echo Stopping server...
>> "%OUTPUT_DIR%\run.bat" echo for /f "tokens=5" %%%%a in ('netstat -ano ^^^| findstr ":8086"') do taskkill /F /PID %%%%a 2^>nul
>> "%OUTPUT_DIR%\run.bat" echo echo Server stopped.

REM Create GUI launcher script
(
echo @echo off
echo REM AAC Assistant - GUI Launcher
echo cd /d "%%~dp0"
echo ^if not exist ".venv\Scripts\pythonw.exe" ^(
echo     echo ERROR: Virtual environment not found.
echo     echo Please run 'install.bat' first.
echo     pause
echo     exit /b 1
echo ^)
echo start "" .venv\Scripts\pythonw launcher.pyw
) > "%OUTPUT_DIR%\start-gui.bat"

REM Create README
echo [7/7] Creating documentation...
(
echo ===================================
echo AAC Assistant %VERSION%
echo ===================================
echo.
echo REQUIREMENTS:
echo   - Python 3.8 or higher
echo   - Node.js 18 or higher ^(for development only^)
echo   - 8GB+ RAM recommended
echo.
echo INSTALLATION:
echo   1. Double-click install.bat
echo   2. Wait for dependencies to install
echo.
echo RUNNING THE APPLICATION:
echo   Option A: Double-click run.bat ^(command line^)
echo   Option B: Double-click start-gui.bat ^(GUI launcher^)
echo.
echo DEFAULT PORTS:
echo   - Backend API: http://localhost:8086
echo   - API Documentation: http://localhost:8086/docs
echo.
echo TROUBLESHOOTING:
echo   - If the application doesn't start, ensure Python and Node.js are installed
echo   - Check the logs folder for error details
echo   - Make sure ports 8086 is not in use by other applications
echo.
echo For more information, visit:
echo https://github.com/your-repo/aac-assistant
echo.
) > "%OUTPUT_DIR%\README.txt"

echo.
echo ===================================
echo Build Complete!
echo ===================================
echo.
echo Package created at: dist\%PACKAGE_NAME%
echo.
echo Contents:
dir /b "%OUTPUT_DIR%"
echo.
echo To distribute:
echo   1. Zip the 'dist\%PACKAGE_NAME%' folder
echo   2. Share the zip file with users
echo   3. Users run 'install.bat' then 'run.bat'
echo.
echo ===================================
