@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
set "PYTHON_ARGS="

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_CMD=.venv\Scripts\python.exe"
  goto launch
)

py -3.14 --version >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py"
  set "PYTHON_ARGS=-3.14"
  goto launch
)
py -3.13 --version >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py"
  set "PYTHON_ARGS=-3.13"
  goto launch
)
py -3.12 --version >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py"
  set "PYTHON_ARGS=-3.12"
  goto launch
)
py -3.11 --version >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py"
  set "PYTHON_ARGS=-3.11"
  goto launch
)
py -3.10 --version >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py"
  set "PYTHON_ARGS=-3.10"
  goto launch
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  goto launch
)

echo.
echo Python was not found. Preparing a portable copy automatically...
echo This does not require administrator rights or pip.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap-python.ps1"
if errorlevel 1 (
  echo.
  echo Automatic Python setup failed.
  echo Check your internet connection and try again, or install Python manually:
  echo https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist "%~dp0.runtime\python-3.14.10\python.exe" (
  echo Portable Python was not found after setup.
  pause
  exit /b 1
)
set "PYTHON_CMD=%~dp0.runtime\python-3.14.10\python.exe"

:launch
echo Starting Genomic Detective...
"%PYTHON_CMD%" %PYTHON_ARGS% -m genomic_detective serve --open
if errorlevel 1 (
  echo.
  echo The application stopped with an error. See the message above.
  pause
)
endlocal
