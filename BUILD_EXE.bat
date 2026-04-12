@echo off
:: PTZ Auto-Tracker — EXE Builder
:: Run this once to produce dist\Trackmind.exe
:: Requires: pip install pyinstaller (handled below)

echo ============================================
echo  PTZ Auto-Tracker — Build EXE
echo ============================================
echo.

:: Install PyInstaller if not present
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

:: Clean previous build
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
if exist PTZ_AutoTracker.spec del PTZ_AutoTracker.spec

echo.
echo Building executable...
echo This may take 2-5 minutes.
echo.

:: Get mediapipe and cv2 package locations for data files
for /f "delims=" %%i in ('python -c "import mediapipe; import os; print(os.path.dirname(mediapipe.__file__))"') do set MP_PATH=%%i
for /f "delims=" %%i in ('python -c "import cv2; import os; print(os.path.dirname(cv2.__file__))"') do set CV2_PATH=%%i

echo MediaPipe path: %MP_PATH%
echo OpenCV path:    %CV2_PATH%
echo.

pyinstaller ^
  --onefile ^
  --windowed ^
  --name "Trackmind" ^
  --icon trackmind_icon.ico ^
  --add-data "trackmind_icon.ico;." ^
  --add-data "%MP_PATH%\modules;mediapipe\modules" ^
  --add-data "%MP_PATH%\python\solutions;mediapipe\python\solutions" ^
  --add-data "%CV2_PATH%\data;cv2\data" ^
  --hidden-import mediapipe ^
  --hidden-import mediapipe.python ^
  --hidden-import mediapipe.python.solutions ^
  --hidden-import mediapipe.python.solutions.pose ^
  --hidden-import cv2 ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageTk ^
  --hidden-import numpy ^
  --collect-all mediapipe ^
  --collect-all cv2 ^
  autotrack.py

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
echo Copy Trackmind.exe to any Windows PC
echo and run it — no Python install needed.
echo.
pause
