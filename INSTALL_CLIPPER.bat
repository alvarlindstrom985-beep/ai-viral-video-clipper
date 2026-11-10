@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo AI Viral Video Clipper - installation
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3 is not installed or not on PATH.
        echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
        echo During installation, enable "Add python.exe to PATH".
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo Could not create the virtual environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 (
    echo Could not update pip.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

echo.
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo WARNING: FFmpeg was not found.
    echo Install FFmpeg and make sure ffmpeg.exe and ffprobe.exe are on PATH.
    echo Download: https://ffmpeg.org/download.html
) else (
    where ffprobe >nul 2>nul
    if errorlevel 1 (
        echo WARNING: ffprobe was not found on PATH.
        echo Install an FFmpeg build that includes both ffmpeg.exe and ffprobe.exe.
    ) else (
        echo FFmpeg and FFprobe were found.
    )
)

echo.
echo Installation finished. Next, double-click START_CLIPPER.bat.
echo Optional speech recognition: install requirements-ai.txt for better reaction/transcript analysis.
echo Optional visual cues: install requirements-vision.txt.
pause
