@echo off
chcp 936 >nul
echo ==========================================
echo CPQ Platform 一键启动
echo ==========================================
echo.

REM 检查 PostgreSQL 服务
echo [0/3] 检查 PostgreSQL 服务...
sc query postgresql-x64-18 | find "RUNNING" >nul
if %errorlevel% neq 0 (
    echo PostgreSQL 未运行，尝试启动...
    net start postgresql-x64-18 >nul 2>&1
    if %errorlevel% neq 0 (
        echo [警告] 无法启动 PostgreSQL，请手动检查服务
    ) else (
        echo PostgreSQL 已启动
    )
) else (
    echo PostgreSQL 已运行
)
echo.

REM 清理旧后端（防重复运行堆实例）：停掉所有 uvicorn 进程 + 占用 8000 的进程
echo [0.5/3] 清理旧后端进程...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'uvicorn|spawn_main' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500; Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; exit 0"
timeout /t 2 >nul

REM 启动后端
echo [1/3] 启动后端服务...
REM 优先用项目自带 backend\.venv（依赖齐全；hermes 会把裸 python 劫持到它自家缺依赖的 venv）
set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"
set "HERMES_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "PYTHON_CMD="
if exist "%VENV_PY%" set "PYTHON_CMD=%VENV_PY%"
if defined PYTHON_CMD goto :got_python
if exist "%HERMES_PY%" set "PYTHON_CMD=%HERMES_PY%"
if defined PYTHON_CMD goto :got_python
where python >nul 2>&1 && set "PYTHON_CMD=python"
:got_python
if not defined PYTHON_CMD (
    echo [错误] 找不到 Python，请确保已安装或配置环境变量
    pause
    exit /b 1
)
echo 使用 Python: %PYTHON_CMD%
start "CPQ-Backend" /d "%~dp0backend" cmd /k "%PYTHON_CMD% -m uvicorn app.main:app --reload --port 8000"

echo 等待后端初始化...
timeout /t 3 >nul
echo.

REM 启动前端
echo [2/3] 启动前端服务...
start "CPQ-Frontend" /d "%~dp0frontend" cmd /k "npm run dev"

echo.
echo [3/3] 打开浏览器...
timeout /t 5 >nul
start http://localhost:5173

echo.
echo ==========================================
echo 启动完成！请保持黑色窗口开启。
echo ==========================================
pause
