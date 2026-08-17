@echo off
setlocal
cd /d "%~dp0web"

if not exist "node_modules\vite\bin\vite.js" (
  echo BinSight dependencies are not installed.
  echo Run pnpm install from the web folder, then open this launcher again.
  pause
  exit /b 1
)

start "" "http://127.0.0.1:5173/"
node "node_modules\vite\bin\vite.js" --host 127.0.0.1 --port 5173
