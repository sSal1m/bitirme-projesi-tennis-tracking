@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Once Kurulum.cmd dosyasini calistir.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\pack_pilot.py --dataset datasets\wall --output "."
if errorlevel 1 (
  echo.
  echo Paketleme basarisiz. Yukaridaki mesaji oku.
  pause
  exit /b 1
)
echo.
echo train.zip ve valid.zip hazir. Colab'a yukleyip train_colab.ipynb calistir.
pause
