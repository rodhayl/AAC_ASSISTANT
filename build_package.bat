@echo off
REM AAC Assistant - reproducible PyInstaller + Inno Setup release build.
REM Requires uv, npm, and Inno Setup 6.7.3 (per-user install is supported).

setlocal
cd /d "%~dp0"

set "VERSION=2.0.0"
set "APP_DIR=dist\AAC_Assistant"
set "INSTALLER=dist\AAC_Assistant_Setup_%VERSION%.exe"
set "ISCC_EXE=C:\Users\rulfe\AppData\Local\Programs\Inno Setup 6\ISCC.exe"

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

if not exist "%ISCC_EXE%" (
    where ISCC.exe >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Inno Setup compiler was not found.
        echo Expected: %ISCC_EXE%
        exit /b 1
    )
    set "ISCC_EXE=ISCC.exe"
)

echo [1/4] Building the frontend...
call npm --prefix src\frontend run build
if errorlevel 1 (
    echo ERROR: Frontend build failed.
    exit /b 1
)

echo [2/4] Building the PyInstaller onedir package...
if exist "%APP_DIR%\uploads\*" (
    echo ERROR: Existing uploads found under %APP_DIR%.
    echo Stop using this portable copy and move user uploads before rebuilding.
    exit /b 1
)
if exist "%APP_DIR%\data\*.db" (
    echo ERROR: Existing database found under %APP_DIR%.
    echo Stop using this portable copy and move user data before rebuilding.
    exit /b 1
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

echo [3/4] Compiling the Inno Setup installer...
call "%ISCC_EXE%" installer.iss
if errorlevel 1 (
    echo ERROR: Inno Setup compilation failed.
    exit /b 1
)
if not exist "%INSTALLER%" (
    echo ERROR: Missing %INSTALLER%
    exit /b 1
)

for %%F in ("%INSTALLER%") do echo       Installer bytes: %%~zF

echo [4/4] Package build complete.
echo       App: %APP_DIR%
echo       Installer: %INSTALLER%
exit /b 0
