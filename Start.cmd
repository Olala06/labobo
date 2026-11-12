@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
  goto launch
)

py -3.11 --version >nul 2>&1
if not errorlevel 1 (
  set "PYTHON=py -3.11"
  goto launch
)
py -3.10 --version >nul 2>&1
if not errorlevel 1 (
  set "PYTHON=py -3.10"
  goto launch
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON=python"
  goto launch
)

echo Python 3.10 or newer was not found.
echo Install Python from https://www.python.org/downloads/ and run Start.cmd again.
pause
exit /b 1

:launch
%PYTHON% -m genomic_detective serve --open
if errorlevel 1 (
  echo.
  echo The application stopped with an error. See the message above.
  pause
)
endlocal
