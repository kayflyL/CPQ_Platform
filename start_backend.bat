@echo off
cd /d "%~dp0backend"
echo Starting Backend...
REM Try common Python locations, fall back to PATH
where python >nul 2>&1
if %errorlevel%==0 (
    python -m uvicorn app.main:app --reload --port 8000
) else (
    if exist "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" (
        "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
    ) else (
        echo Error: Python not found. Please ensure Python is installed and in PATH.
    )
)
pause
