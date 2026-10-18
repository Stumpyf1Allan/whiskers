@echo off
REM Try Whiskers 1.1 from this folder WITHOUT touching your real Whiskers.
REM
REM It keeps everything in its own folder, %LOCALAPPDATA%\Whiskers 1.1 test, so your
REM own Whiskers (and the family's copies) carry on exactly as before. Delete that
REM folder to start the test again from nothing.
REM
REM Needs Python 3.10+ from python.org with "Add Python to PATH" ticked.
cd /d "%~dp0"
set "WHISKERS_DATA_DIR=%LOCALAPPDATA%\Whiskers 1.1 test"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add Python to PATH", then double-click this again.
  pause
  exit /b 1
)
if not exist ".venv" python -m venv .venv
call .venv\Scripts\activate.bat
if not exist ".venv\installed.ok" (
  echo Setting up, about a minute...
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Some extras didn't install. Whiskers will still run, with fewer of them.
    echo Copy the messages above into a chat with Claude.
    pause
  ) else (
    echo ok> ".venv\installed.ok"
  )
)
echo Whiskers 1.1 test copy. Its data folder is "%WHISKERS_DATA_DIR%".
python run_whiskers.py
if errorlevel 1 pause
