@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0start.ps1" (
  echo Please extract the ENTIRE project ZIP before running Start.cmd.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
  echo.
  echo See the error above. Check your internet connection or install Python manually.
  echo Help: README.md
  pause
  exit /b 1
)
