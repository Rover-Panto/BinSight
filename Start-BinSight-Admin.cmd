@echo off
setlocal
cd /d "%~dp0admin-portal"

if not exist ".venv\Scripts\python.exe" (
  echo BinSight admin dependencies are not installed.
  echo Run Setup-BinSight-Admin.cmd from the repository root first.
  pause
  exit /b 1
)

echo Checking BinSight local readiness...
".venv\Scripts\python.exe" -m binsight.cli health > "data\startup-health.json"
if errorlevel 1 (
  echo BinSight is not ready. Review admin-portal\data\startup-health.json.
  type "data\startup-health.json"
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8501/"
".venv\Scripts\python.exe" -m streamlit run app.py
