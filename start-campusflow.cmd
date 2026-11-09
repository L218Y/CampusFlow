@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
if not exist "dist\index.html" (
    call npm.cmd run build
    if errorlevel 1 goto failed
)
echo CampusFlow is starting at http://127.0.0.1:8000
echo Open the address in your browser. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto failed
exit /b 0
:missing
echo Python dependencies are missing. See README.md for setup.
:failed
pause
exit /b 1
