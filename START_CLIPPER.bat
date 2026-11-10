@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The app has not been installed yet. Run INSTALL_CLIPPER.bat first.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo FFmpeg is missing from PATH. Install FFmpeg first:
    echo https://ffmpeg.org/download.html
    pause
    exit /b 1
)
where ffprobe >nul 2>nul
if errorlevel 1 (
    echo FFprobe is missing from PATH. Install an FFmpeg build that includes ffprobe.
    pause
    exit /b 1
)

echo Starting AI Viral Video Clipper...
echo Keep this window open while the clipper is running.
echo Dashboard: http://127.0.0.1:8000
echo Press Ctrl+C in this window to stop the app.
echo.

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Clipper stopped.
pause
