@echo off
setlocal
cd /d "%~dp0"

where go >nul 2>nul
if errorlevel 1 (
  echo Go is required to build the Windows launcher.
  pause
  exit /b 1
)

rem Bundle the renderer for the launcher's private Python 3.12 Windows runtime.
rem pip retains upstream wheel metadata and third-party license notices.
py -3 -m pip install --upgrade --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp --abi cp312 --target app\vendor -r requirements.txt
if errorlevel 1 exit /b 1

rem Standard ZIP names avoid PowerShell's inconsistent directory entries.
py -3 launcher\build_bundle.py
if errorlevel 1 exit /b 1

cd launcher
set GOOS=windows
set GOARCH=amd64
set CGO_ENABLED=0
echo Checking launcher installation...
go test install.go archive.go install_test.go
if errorlevel 1 (
  echo Launcher checks failed. No new EXE was built.
  pause
  exit /b 1
)
go build -trimpath -ldflags "-H=windowsgui -s -w" -o ..\Atlas_Tools_Label_Sheet_Builder.exe .
if errorlevel 1 exit /b 1

echo.
echo Built Atlas_Tools_Label_Sheet_Builder.exe
pause
