@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -e ".[dev,pose]"
if errorlevel 1 goto fail
".venv\Scripts\python.exe" scripts\download_pose.py
if errorlevel 1 goto fail
echo Kurulum tamamlandi. Baslat.cmd ile acabilirsin.
pause
exit /b 0
:fail
echo Kurulum tamamlanamadi. Yukaridaki hata mesajini kontrol et.
pause
exit /b 1
