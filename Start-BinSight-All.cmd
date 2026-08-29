@echo off
setlocal

if not exist "%~dp0web\node_modules\vite\bin\vite.js" (
  echo Citizen frontend dependencies are not installed.
  echo Run pnpm install from the web folder first.
  pause
  exit /b 1
)

if not exist "%~dp0admin-portal\.venv\Scripts\python.exe" (
  echo Admin portal dependencies are not installed.
  echo Run Setup-BinSight-Admin.cmd first.
  pause
  exit /b 1
)

start "BinSight Citizen Frontend" "%ComSpec%" /k call "%~dp0Start-BinSight.cmd"
start "BinSight Admin Portal" "%ComSpec%" /k call "%~dp0Start-BinSight-Admin.cmd"
