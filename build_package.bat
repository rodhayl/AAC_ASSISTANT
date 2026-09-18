@echo off
REM AAC Assistant - reproducible PyInstaller + Inno Setup release build.
REM Requires uv, npm, and Inno Setup 6.7.3 (per-user install is supported).
REM Set AAC_SIGN_RELEASE=1 to also Authenticode-sign the binaries with the
REM free self-signed certificate managed by scripts\sign_release.ps1.

setlocal
cd /d "%~dp0"

REM The release version has a single source, pyproject.toml. It is passed to
REM Inno Setup below so installer.iss never duplicates the number.
for /f "delims=" %%V in ('uv version --short') do set "VERSION=%%V"
if not defined VERSION (
    echo ERROR: Could not read the project version from pyproject.toml via uv.
    exit /b 1
)
set "APP_DIR=dist\AAC_Assistant"
set "INSTALLER=dist\AAC_Assistant_Setup_%VERSION%.exe"
set "ISCC_EXE="
if defined INNO_SETUP_PATH set "ISCC_EXE=%INNO_SETUP_PATH:"=%"
if not defined ISCC_EXE if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%SystemDrive%\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%SystemDrive%\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE (
    where ISCC.exe >nul 2>&1
    if not errorlevel 1 set "ISCC_EXE=ISCC.exe"
)

if not exist ".env.example" (
    echo ERROR: .env.example is missing.
    exit /b 1
)
where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv is not installed or not on PATH.
    exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm is not installed or not on PATH.
    exit /b 1
)

if not defined ISCC_EXE (
    echo ERROR: Inno Setup compiler was not found.
    echo Install Inno Setup 6.7.3 or set INNO_SETUP_PATH to ISCC.exe.
    exit /b 1
)
if /i "%ISCC_EXE%"=="ISCC.exe" goto :iscc_validated
if exist "%ISCC_EXE%" goto :iscc_validated
echo ERROR: Configured Inno Setup compiler does not exist: %ISCC_EXE%
exit /b 1

:iscc_validated

echo [1/6] Syncing Python dependencies (voice and TTS extras)...
call uv sync --extra voice --extra tts
if errorlevel 1 (
    echo ERROR: uv sync failed.
    exit /b 1
)

echo [2/6] Downloading offline AI models into the bundle...
call uv run python scripts\bundle_models.py
if errorlevel 1 (
    echo ERROR: Model download failed.
    exit /b 1
)

echo [3/6] Installing frontend dependencies and building...
if not exist "src\frontend\node_modules" (
    call npm --prefix src\frontend ci --prefer-offline --no-audit --no-fund
    if errorlevel 1 (
        echo ERROR: npm ci failed.
        exit /b 1
    )
)
call npm --prefix src\frontend run build
if errorlevel 1 (
    echo ERROR: Frontend build failed.
    exit /b 1
)

echo [4/6] Building the PyInstaller onedir package...
if exist "%APP_DIR%\.env" (
    echo ERROR: Existing runtime config found under %APP_DIR%.
    echo Stop using this portable copy and move .env before rebuilding.
    exit /b 1
)
if exist "%APP_DIR%\env.properties" (
    echo ERROR: Existing legacy runtime config found under %APP_DIR%.
    echo Stop using this portable copy and move env.properties before rebuilding.
    exit /b 1
)
if exist "%APP_DIR%\uploads\" (
    dir /b /s /a-d "%APP_DIR%\uploads\*" >nul 2>&1
    if not errorlevel 1 (
        echo ERROR: Existing uploads found under %APP_DIR%.
        echo Stop using this portable copy and move user uploads before rebuilding.
        exit /b 1
    )
)
if exist "%APP_DIR%\data\" (
    dir /b /s /a-d "%APP_DIR%\data\*" >nul 2>&1
    if not errorlevel 1 (
        echo ERROR: Existing runtime data found under %APP_DIR%.
        echo Stop using this portable copy and move all user data before rebuilding.
        exit /b 1
    )
)
if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"
if exist "build\AAC_Assistant" rmdir /s /q "build\AAC_Assistant"
call uv run pyinstaller AAC_Assistant.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    exit /b 1
)
if not exist "%APP_DIR%\AAC_Assistant.exe" (
    echo ERROR: Missing %APP_DIR%\AAC_Assistant.exe
    exit /b 1
)

for /f %%S in ('powershell -NoProfile -Command "(Get-ChildItem -LiteralPath %APP_DIR% -Recurse -File | Measure-Object -Property Length -Sum).Sum"') do set "DIST_BYTES=%%S"
echo       Onedir output bytes: %DIST_BYTES%

echo [5/6] Compiling the Inno Setup installer...
call "%ISCC_EXE%" /DMyAppVersion=%VERSION% installer.iss
if errorlevel 1 (
    echo ERROR: Inno Setup compilation failed.
    exit /b 1
)
if not exist "%INSTALLER%" (
    echo ERROR: Missing %INSTALLER%
    exit /b 1
)

for %%F in ("%INSTALLER%") do echo       Installer bytes: %%~zF

if "%AAC_SIGN_RELEASE%"=="1" (
    echo [6/6] Signing release binaries with Authenticode...
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sign_release.ps1 -ExePath "%APP_DIR%\AAC_Assistant.exe" -InstallerPath "%INSTALLER%"
    if errorlevel 1 (
        echo WARNING: Code signing failed; continuing with unsigned binaries.
    )
) else (
    echo [6/6] Skipping code signing ^(set AAC_SIGN_RELEASE=1 to enable^).
)

echo [6/6] Package build complete.
echo       App: %APP_DIR%
echo       Installer: %INSTALLER%
exit /b 0
