@echo off
setlocal
title CPQ 更新发布(10.32.39.132)

echo [1/4] 构建前端(1-2 分钟)...
cd /d "%~dp0..\frontend"
call npm run build || (echo 前端构建失败,先在本地把报错修掉 & pause & exit /b 1)

echo [2/4] 打包...
if not exist D:\CPQ_Archive mkdir D:\CPQ_Archive
tar czf D:\CPQ_Archive\dist.tgz -C dist .
tar czf D:\CPQ_Archive\backend.tgz --exclude=.venv --exclude=.env --exclude=__pycache__ --exclude=tmp --exclude=*.db --exclude=storage --exclude=_backups --exclude=_backup* -C .. backend

echo [3/4] 上传(免密)...
scp D:\CPQ_Archive\backend.tgz D:\CPQ_Archive\dist.tgz 10.32.39.132:cpq/ || (echo 上传失败:检查网络与服务器可达 & pause & exit /b 1)
scp "%~dp0userspace\web.js" "%~dp0userspace\start.sh" "%~dp0userspace\make_certs.sh" "%~dp0userspace\update.sh" 10.32.39.132:cpq/ || (echo 上传失败:检查网络与服务器可达 & pause & exit /b 1)

echo [4/4] 服务器落位并重启后端(约半分钟)...
ssh 10.32.39.132 "bash ~/cpq/update.sh" || (echo 服务器执行失败,看上面报错 & pause & exit /b 1)

echo.
echo 发布完成!浏览器打开 http://10.32.39.132:5173 验证。
echo 服务器数据库结构变更会在重启时自动迁移;若代码新增了配置项,需手动补 ~/cpq/backend/.env
pause
