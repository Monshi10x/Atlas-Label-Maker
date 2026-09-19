@echo off
setlocal
cd /d "%~dp0"

where go >nul 2>nul
if errorlevel 1 (
  echo Go is required to build the Windows launcher.
  pause
  exit /b 1
)

if exist launcher\app_bundle.zip del /q launcher\app_bundle.zip
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'app\*' -DestinationPath 'launcher\app_bundle.zip' -CompressionLevel Optimal"
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
