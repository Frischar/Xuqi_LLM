@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [First run] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Please make sure Python is installed.
        pause
        exit /b 1
    )
)

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
)

echo [Startup] Installing or checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

start "" "http://127.0.0.1:8000"
echo [Startup] Launching WebUI. Closing this window will stop the server.
".venv\Scripts\python.exe" -m uvicorn app:app --reload --host 127.0.0.1 --port 8000

pause
