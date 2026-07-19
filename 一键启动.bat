@echo off
chcp 65001 >nul
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

REM 启动后端
echo [1/3] 启动后端服务...
where python >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
) else (
    if exist "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" (
        set "PYTHON_CMD=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
    ) else (
        echo [错误] 找不到 Python，请确保已安装或配置环境变量
        pause
        exit /b 1
    )
)
start "CPQ-Backend" cmd /k "cd /d %~dp0backend && "%PYTHON_CMD%" -m uvicorn app.main:app --reload --port 8000"

echo 等待后端初始化...
timeout /t 3 >nul
echo.

REM 启动前端
echo [2/3] 启动前端服务...
start "CPQ-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo [3/3] 打开浏览器...
timeout /t 5 >nul
start http://localhost:5173

echo.
echo ==========================================
echo 启动完成！请保持黑色窗口开启。
echo ==========================================
pause
