@echo off
echo ============================================
echo  TrackMind — Build EXE
echo ============================================
echo.

:: Install / upgrade dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Check your Python/pip setup.
    pause
    exit /b 1
)

:: Clean previous build artifacts
echo Cleaning previous build...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist

:: Write current git tag to version.txt (bundled into the exe)
echo Writing version...
for /f "tokens=*" %%i in ('git describe --tags --abbrev=0 2^>nul') do set GIT_TAG=%%i
if "%GIT_TAG%"=="" set GIT_TAG=unknown
echo %GIT_TAG%> version.txt
echo Version: %GIT_TAG%
echo.

echo Building Trackmind.exe  ^(this takes 3-6 minutes^)...
echo.

pyinstaller Trackmind.spec

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  BUILD COMPLETE
echo  Output: dist\Trackmind.exe
echo ============================================
echo.
echo You can now run dist\Trackmind.exe directly
echo or run BUILD_INSTALLER.bat to create a setup package.
echo.
pause
