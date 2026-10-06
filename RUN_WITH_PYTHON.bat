@echo off
cd /d "%~dp0"
py -3 -m pip install --upgrade --no-deps --only-binary=:all: --target app\vendor -r requirements.txt
if errorlevel 1 exit /b 1
py -3 app\atlas_label_maker.py --open-browser --data-root "%LOCALAPPDATA%\Atlas Tools Label Maker"
pause
