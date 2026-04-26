@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [Build] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [Build] Installing runtime dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install runtime dependencies.
    pause
    exit /b 1
)

echo [Build] Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [Build] Packaging launcher...
".venv\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name XuqiLauncher ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "data;data" ^
  --add-data "cards;cards" ^
  launcher.py

if errorlevel 1 (
    echo Packaging failed.
    pause
    exit /b 1
)

echo [Build] Done. Output file: %cd%\dist\XuqiLauncher.exe
pause
