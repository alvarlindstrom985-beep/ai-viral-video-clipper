@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo AI Viral Video Clipper - setup check
echo ==========================================
echo.

set "HAS_ERROR=0"

where py >nul 2>nul
if not errorlevel 1 (
    echo [OK] Python launcher found.
    py -3 --version
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python 3 not found. Install Python 3.10+ from https://www.python.org/downloads/windows/
        set "HAS_ERROR=1"
    ) else (
        echo [OK] Python found.
        python --version
    )
)

if exist ".venv\Scripts\python.exe" (
    echo [OK] Project virtual environment exists.
    ".venv\Scripts\python.exe" --version
) else (
    echo [WARNING] Virtual environment not created yet. Run INSTALL_CLIPPER.bat.
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [ERROR] FFmpeg not found on PATH.
    set "HAS_ERROR=1"
) else (
    echo [OK] FFmpeg found.
    ffmpeg -version | findstr /B /C:"ffmpeg version"
)

where ffprobe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] FFprobe not found on PATH.
    set "HAS_ERROR=1"
) else (
    echo [OK] FFprobe found.
    ffprobe -version | findstr /B /C:"ffprobe version"
)

set "ODROOT="
if not "%OneDrive%"=="" set "ODROOT=%OneDrive%"
if "%ODROOT%"=="" if not "%OneDriveCommercial%"=="" set "ODROOT=%OneDriveCommercial%"
if "%ODROOT%"=="" if not "%OneDriveConsumer%"=="" set "ODROOT=%OneDriveConsumer%"

if not "%ODROOT%"=="" (
    set "INBOX=%ODROOT%\AI Viral Video Clipper\Inbox"
    echo.
    echo [OK] OneDrive sync root detected:
    echo "%ODROOT%"
    if not exist "%INBOX%" (
        echo [WARNING] Expected Inbox folder is missing:
        echo "%INBOX%"
        echo Create it in OneDrive or let the app create it on first launch.
    ) else (
        echo [OK] Clipper Inbox folder exists:
        echo "%INBOX%"
    )
) else (
    echo.
    echo [WARNING] No OneDrive environment variable detected for this Windows session.
    echo The app will use its local source_inbox folder unless CLIPPER_SOURCE_INBOX is configured.
    echo If OneDrive is installed, sign in and reopen this window.
)

echo.
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARNING] Port 8000 is already in use. Stop the other app before starting the clipper.
) else (
    echo [OK] Port 8000 appears available.
)

echo.
if "%HAS_ERROR%"=="1" (
    echo One or more required components need attention.
) else (
    echo Required command checks completed. Review any warnings above.
)
echo.
echo Next: run INSTALL_CLIPPER.bat once, then START_CLIPPER.bat.
pause
