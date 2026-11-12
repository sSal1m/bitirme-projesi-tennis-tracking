@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Once Kurulum.cmd dosyasini calistir.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m tennis_tracking.app
if errorlevel 1 pause
