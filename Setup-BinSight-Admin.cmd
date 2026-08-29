@echo off
setlocal
cd /d "%~dp0admin-portal"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.12 or 3.13, then run this setup again.
  pause
  exit /b 1
)

set "BINSIGHT_PYTHON_SELECTOR="
py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>nul
if not errorlevel 1 set "BINSIGHT_PYTHON_SELECTOR=-3.13"
if not defined BINSIGHT_PYTHON_SELECTOR (
  py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 set "BINSIGHT_PYTHON_SELECTOR=-3.12"
)
if not defined BINSIGHT_PYTHON_SELECTOR (
  echo Python 3.12 or 3.13 was not found.
  echo Install a supported Python from https://www.python.org/downloads/ and enable the py launcher.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the BinSight admin Python environment...
  py %BINSIGHT_PYTHON_SELECTOR% -m venv .venv
  if errorlevel 1 exit /b 1
)

echo Installing BinSight admin dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Admin portal setup is complete.
echo Run Start-BinSight-Admin.cmd from the repository root.
pause
