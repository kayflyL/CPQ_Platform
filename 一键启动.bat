@echo off
echo [1/3] Starting Backend Server...
start "CPQ-Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --reload --port 8000"

echo Waiting for Backend to initialize...
timeout /t 3 >nul

echo [2/3] Starting Frontend Server...
start "CPQ-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo [3/3] Opening Browser...
timeout /t 5 >nul
start http://localhost:5173

echo ==========================================
echo System started. Keep the black windows open.
echo ==========================================
pause
