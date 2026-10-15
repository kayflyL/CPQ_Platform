@echo off
setlocal
title CPQ 首次部署

rem ===== 前置:deploy\server.txt 里写一行 用户名@服务器IP =====
if not exist "%~dp0server.txt" (
  echo 缺少 deploy\server.txt,请建一个并写入一行: 用户名@服务器IP
  pause & exit /b 1
)
set /p SERVER=<"%~dp0server.txt"
if not "%SERVER:改成=%"=="%SERVER%" (
  echo 请先把 deploy\server.txt 里的占位改成: 用户名@服务器IP
  pause & exit /b 1
)
echo 目标服务器: %SERVER%
where ssh >nul 2>&1 || (echo 未找到 ssh/scp:Windows 设置-应用-可选功能-添加 OpenSSH 客户端 & pause & exit /b 1)

echo [1/6] 构建前端(1-2 分钟)...
cd /d "%~dp0..\frontend"
call npm run build || (echo 前端构建失败,先在本地把报错修掉 & pause & exit /b 1)

echo [2/6] 打包到 D:\CPQ_Archive ...
if not exist D:\CPQ_Archive mkdir D:\CPQ_Archive
tar czf D:\CPQ_Archive\cpq_frontend_dist.tgz -C dist .
tar czf D:\CPQ_Archive\cpq_backend.tgz --exclude=.venv --exclude=.env --exclude=__pycache__ --exclude=tmp --exclude=*.db -C .. backend
tar czf D:\CPQ_Archive\cpq_data.tgz -C D:\Quotation_Automation config.json
tar czf D:\CPQ_Archive\cpq_deploy.tgz -C .. deploy

echo [3/6] 导出开发库(要输一次开发机 PostgreSQL 的 postgres 密码,输入会回显,本机自用无妨)...
set "PGDUMP="
for %%P in ("%ProgramFiles%\PostgreSQL\18\bin\pg_dump.exe" "%ProgramFiles%\PostgreSQL\17\bin\pg_dump.exe" "%ProgramFiles%\PostgreSQL\16\bin\pg_dump.exe") do if exist %%P set "PGDUMP=%%~P"
if not defined PGDUMP (echo 没找到 pg_dump,请确认装了 PostgreSQL & pause & exit /b 1)
for /f %%i in ('powershell -NoProfile -Command Get-Date -Format yyyyMMdd') do set TS=%%i
set "DUMPFILE=D:\CPQ_Archive\cpq_platform_%TS%.dump"
set /p PGPASSWORD=postgres 密码:
"%PGDUMP%" -U postgres -d cpq_platform -F c --no-owner --no-privileges -f "%DUMPFILE%" || (echo 库导出失败(多半是密码不对) & pause & exit /b 1)
set PGPASSWORD=

echo [4/6] 收集 LLM 配置(取自 backend\.env,不入仓库)...
findstr /B "LLM_API_KEY= LLM_BASE_URL= LLM_MODEL= FIRECRAWL_API_KEY=" "%~dp0..\backend\.env" > "%TEMP%\cpq_secrets.env"

echo [5/6] 上传到 %SERVER% (输一次密码)...
scp "%DUMPFILE%" "%TEMP%\cpq_secrets.env" D:\CPQ_Archive\cpq_backend.tgz D:\CPQ_Archive\cpq_frontend_dist.tgz D:\CPQ_Archive\cpq_data.tgz D:\CPQ_Archive\cpq_deploy.tgz %SERVER%:/tmp/ || (echo 上传失败:检查 server.txt 的地址和服务器 SSH 可达性 & pause & exit /b 1)

echo [6/6] 服务器自动安装(装 PostgreSQL/依赖/chromium,几分钟,中间可能要输 sudo 密码)...
ssh -t %SERVER% "tar xzf /tmp/cpq_deploy.tgz -C /tmp && sed -i 's/\r$//' /tmp/deploy/server_setup.sh && sudo bash /tmp/deploy/server_setup.sh" || (echo 服务器执行失败,看上面报错 & pause & exit /b 1)

echo.
echo 完成!浏览器打开脚本末尾打印的 http://IP ,按 deploy\DEPLOY.md 的验证清单逐条打勾。
pause
