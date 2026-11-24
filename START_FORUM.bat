@echo off
title DDS Creations Forum
cd /d "%~dp0forum"
echo.
echo  ===== DDS Creations Forum =====
echo  Installing Flask (first run only)...
python -m pip install --quiet flask
if errorlevel 1 (
  echo.
  echo  Python was not found. Install it from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" during setup, then run this file again.
  pause
  exit /b
)
set VV_ADMIN=mathesh
echo  Starting... your browser will open at http://127.0.0.1:5000
echo  Keep this window open while you use the forum. Close it to stop.
start "" http://127.0.0.1:5000
python app.py
pause
