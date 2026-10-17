@echo off
rem Build Dayplayer.exe, run this on a Windows machine with Python 3.11+.
rem Result: dist\Circadia.exe (single file, no install needed).
python -m venv .venv || goto :err
.venv\Scripts\pip install -q -r requirements.txt pyinstaller || goto :err
.venv\Scripts\pyinstaller --noconfirm --name Circadia --onefile --windowed ^
    --icon assets\icon.ico --add-data "assets;assets" ^
    --hidden-import pystray._win32 ^
    --hidden-import dayplayer.dashboard --hidden-import dayplayer.livewindow --hidden-import dayplayer.onboarding run_dayplayer.py
if errorlevel 1 goto :err
echo.
echo Done. Your app: dist\Circadia.exe
pause
exit /b 0
:err
echo Build failed.
pause
exit /b 1
