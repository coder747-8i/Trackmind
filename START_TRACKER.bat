@echo off
:: PTZOptics Auto-Tracker Launcher
:: Edit the values below to match your setup, then double-click to run.

:: ── YOUR SETTINGS ────────────────────────────────────────────
set CAMERA_IP=192.168.1.10
set RTSP_USER=admin
set RTSP_PASS=admin
set RTSP_STREAM=2
set HOME_PRESET=5
:: ─────────────────────────────────────────────────────────────
:: RTSP_STREAM: 1 = main stream (1080p, more latency)
::              2 = sub stream  (lower res, less latency) ← recommended
:: ─────────────────────────────────────────────────────────────

echo Starting PTZ Auto-Tracker...
echo Camera IP   : %CAMERA_IP%
echo RTSP stream : %RTSP_STREAM% (1=main, 2=sub)
echo Home preset : %HOME_PRESET%
echo.
echo Press Q in the preview window to quit.
echo Press SPACE to pause/resume tracking.
echo.

python autotrack.py ^
    --camera-ip %CAMERA_IP% ^
    --rtsp-user %RTSP_USER% ^
    --rtsp-pass %RTSP_PASS% ^
    --rtsp-stream %RTSP_STREAM% ^
    --home-preset %HOME_PRESET%

pause
