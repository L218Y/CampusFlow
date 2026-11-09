@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if errorlevel 1 goto prerequisites
where npm.cmd >nul 2>nul
if errorlevel 1 goto prerequisites
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto prerequisites
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 22 ? 0 : 1)"
if errorlevel 1 goto prerequisites

if not exist ".cache\tmp" mkdir ".cache\tmp"
if errorlevel 1 goto failed
set "TEMP=%CD%\.cache\tmp"
set "TMP=%TEMP%"

echo [1/3] Installing Python dependencies...
if not exist ".venv\Scripts\python.exe" (
    python -m venv ".venv"
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt" --index-url https://pypi.org/simple --cache-dir ".cache\pip"
if errorlevel 1 goto failed

echo [2/3] Installing frontend dependencies...
call npm.cmd ci --registry https://registry.npmjs.org --cache ".cache\npm"
if errorlevel 1 goto failed

echo [3/3] Building the application...
call npm.cmd run build
if errorlevel 1 goto failed

if not exist ".env" (
    copy ".env.example" ".env" >nul
    if errorlevel 1 goto failed
)
echo Setup complete. Run start-campusflow.cmd to start CampusFlow.
echo To enable the AI assistant, set DEEPSEEK_API_KEY in .env before starting.
pause
exit /b 0

:prerequisites
echo Please install Python 3.11 or newer and Node.js 22 or newer, then reopen this script.
goto failed

:failed
echo Setup failed. Check the error above and see README.md for setup instructions.
pause
exit /b 1
