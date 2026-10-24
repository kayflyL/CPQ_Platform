@echo off
chcp 936 >nul
title CPQ 系统演示
echo ==========================================
echo   CPQ 系统演示
echo   （会自动拉起未运行的前后端服务）
echo ==========================================
set "CURL=%SystemRoot%\System32\curl.exe"
set "SLEEP=%SystemRoot%\System32\timeout.exe"

REM ── 1. 探测后端与前端的当前状态 ──
set BACKEND_OK=0
"%CURL%" -s -m 2 -o nul "http://127.0.0.1:8000/" >nul 2>&1 && set BACKEND_OK=1
set "FRONT_PORT="
"%CURL%" -s -m 2 -o nul "http://127.0.0.1:3000/%E7%B3%BB%E7%BB%9F%E6%BC%94%E7%A4%BA.html" >nul 2>&1 && set "FRONT_PORT=3000"
if not defined FRONT_PORT "%CURL%" -s -m 2 -o nul "http://127.0.0.1:5173/%E7%B3%BB%E7%BB%9F%E6%BC%94%E7%A4%BA.html" >nul 2>&1 && set "FRONT_PORT=5173"

if "%BACKEND_OK%"=="1" (echo [OK] 后端已在运行) else (echo [--] 后端未运行)
if defined FRONT_PORT (echo [OK] 前端已在运行，端口 %FRONT_PORT%) else (echo [--] 前端未运行)

REM ── 2. 缺哪个就整体拉起一键启动（它自带去重，不会重复起实例）──
if "%BACKEND_OK%"=="0" goto needstart
if not defined FRONT_PORT goto needstart
goto waitready

:needstart
echo.
echo 正在拉起 一键启动.bat（会另开窗口，请勿关闭它）...
start "" "%~dp0一键启动.bat"

REM ── 3. 轮询等待前后端就绪（最多 90 秒）──
:waitready
echo.
echo 等待服务就绪（最多 90 秒）...
set /a TRIES=0
:waitloop
set /a TRIES+=1
set BACKEND_OK=0
set "FRONT_PORT="
"%CURL%" -s -m 2 -o nul "http://127.0.0.1:8000/" >nul 2>&1 && set BACKEND_OK=1
"%CURL%" -s -m 2 -o nul "http://127.0.0.1:3000/%E7%B3%BB%E7%BB%9F%E6%BC%94%E7%A4%BA.html" >nul 2>&1 && set "FRONT_PORT=3000"
if not defined FRONT_PORT "%CURL%" -s -m 2 -o nul "http://127.0.0.1:5173/%E7%B3%BB%E7%BB%9F%E6%BC%94%E7%A4%BA.html" >nul 2>&1 && set "FRONT_PORT=5173"
if "%BACKEND_OK%"=="1" if defined FRONT_PORT goto ready
if %TRIES% geq 45 (
  echo.
  echo [失败] 等了 90 秒服务还没就绪。请看 一键启动.bat 那个窗口报了什么错，
  echo        修好后再运行本脚本。
  pause
  exit /b 1
)
"%SLEEP%" /t 2 >nul
goto waitloop

:ready
echo.
echo [OK] 服务就绪：后端 8000，前端 %FRONT_PORT%
echo 正在打开演示页...
start "" "http://localhost:%FRONT_PORT%/系统演示.html"
echo 已在浏览器打开，本窗口可以关闭了。
"%SLEEP%" /t 4 >nul
exit /b 0
