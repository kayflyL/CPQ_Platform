@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo CPQ Platform 数据库恢复（目标机用）
echo ==========================================
echo.
echo 本脚本把 cpq_platform.dump 恢复到本机 PostgreSQL。
echo 前置: 已安装 PostgreSQL 18 或更高（dump 由 18.4 导出）。
echo.

REM ---- 0. 定位 PostgreSQL bin 目录（自动探测；可用环境变量 PG_BINDIR 覆盖）----
set "PG_BIN=%PG_BINDIR%"
if not defined PG_BIN (
    for /f "delims=" %%D in ('dir /b /ad "C:\Program Files\PostgreSQL" 2^>nul ^| sort') do (
        if exist "C:\Program Files\PostgreSQL\%%D\bin\pg_restore.exe" set "PG_BIN=C:\Program Files\PostgreSQL\%%D\bin"
    )
)
if not defined PG_BIN (
    echo [错误] 找不到 PostgreSQL 安装目录。
    echo        请确认已安装 PostgreSQL 18+；或设置环境变量 PG_BINDIR 指向 bin 目录后重试。
    echo.
    pause & exit /b 1
)
echo 使用 PostgreSQL 工具: %PG_BIN%
echo.

REM ---- 1. 定位 dump 文件（拖拽优先，否则取脚本同目录 cpq_platform.dump）----
set "DUMP=%~1"
if not defined DUMP set "DUMP=%~dp0cpq_platform.dump"
if not exist "%DUMP%" (
    echo [错误] 找不到 dump 文件:
    echo        %DUMP%
    echo.
    echo 用法: 把 cpq_platform.dump 拖到本脚本上运行；
    echo        或把它放到脚本同目录、命名为 cpq_platform.dump。
    echo.
    pause & exit /b 1
)
echo 数据库 dump: %DUMP%
echo.

REM ---- 2. 输入 postgres 密码（仅本次会话；输入明文显示属正常）----
set /p PGPASSWORD=请输入 PostgreSQL 的 postgres 用户密码:
if not defined PGPASSWORD (
    echo [错误] 密码不能为空。
    pause & exit /b 1
)
echo.

REM ---- 3. 检查 cpq_platform 是否已存在（不自动覆盖，避免污染）----
echo [1/3] 检查数据库...
"%PG_BIN%\psql.exe" -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='cpq_platform'" | find "1" >nul
if %errorlevel% equ 0 (
    echo [错误] 数据库 cpq_platform 已存在，本脚本不自动覆盖。
    echo        如需重置，先手动执行:
    echo            "%PG_BIN%\psql.exe" -U postgres -c "DROP DATABASE cpq_platform"
    echo        再重新运行本脚本。
    echo.
    pause & exit /b 1
)
echo      库不存在，继续。
echo.

REM ---- 4. 建库 ----
echo [2/3] 创建数据库 cpq_platform...
"%PG_BIN%\psql.exe" -U postgres -c "CREATE DATABASE cpq_platform" >nul
if %errorlevel% neq 0 (
    echo [错误] 建库失败。请确认 PostgreSQL 服务已启动、密码正确。
    pause & exit /b 1
)
echo      完成。
echo.

REM ---- 5. 恢复（schema + 表 + 序列 + 数据一次全进）----
echo [3/3] 恢复 schema 与数据...
"%PG_BIN%\pg_restore.exe" -U postgres -d cpq_platform --no-owner --no-privileges "%DUMP%"
if %errorlevel% neq 0 (
    echo.
    echo [警告] 恢复过程中出现报错（见上方输出）。常见原因:
    echo        - PostgreSQL 版本低于 18（dump 由 18.4 导出，目标须不低于 18）
    echo        - 缺扩展（报 extension 字样时，先进 cpq_platform 执行 CREATE EXTENSION 再重跑）
    echo        - 部分非致命 warning 可忽略，但请进入应用核对数据是否完整。
    echo.
    pause & exit /b 1
)

echo.
echo ==========================================
echo 数据库恢复成功！
echo 下一步: 安装依赖并启动 —— 双击 一键启动.bat
echo ==========================================
pause
