@echo off
cd /d "%~dp0backend"
echo Starting Backend...
REM Prefer project venv (deps ready); bare python gets hijacked by hermes to a dep-less venv
set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"
set "HERMES_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "PYTHON_CMD="
if exist "%VENV_PY%" set "PYTHON_CMD=%VENV_PY%"
if defined PYTHON_CMD goto :got_python
if exist "%HERMES_PY%" set "PYTHON_CMD=%HERMES_PY%"
if defined PYTHON_CMD goto :got_python
where python >nul 2>&1 && set "PYTHON_CMD=python"
:got_python
set FLOW_VALIDATION_MODE=enforce
REM 流发布闸硬模式：漏声明契约的流保存被 400 拦截（docs/引擎ABI-v0.md 节点契约）
if not defined PYTHON_CMD (
    echo Error: Python not found. Please ensure Python is installed and in PATH.
    pause
    exit /b 1
)
echo Using Python: %PYTHON_CMD%
"%PYTHON_CMD%" -m uvicorn app.main:app --host :: --reload --port 8000
pause
