@echo off
setlocal
cd /d "%~dp0admin-portal"

if not exist ".venv\Scripts\python.exe" (
  echo BinSight admin dependencies are not installed.
  echo Run Setup-BinSight-Admin.cmd from the repository root first.
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8501/"
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
