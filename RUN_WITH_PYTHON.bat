@echo off
cd /d "%~dp0"
py -3 app\atlas_label_maker.py --open-browser --data-root "%LOCALAPPDATA%\Atlas Tools Label Maker"
pause
