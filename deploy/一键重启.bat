@echo off
setlocal
title CPQ 重启服务(10.32.39.132)

echo 重启后端服务(数据库不动,前端静态即改即生效),约半分钟...
echo 若刚发布过更新,后端已在 update 流程里重启过,无需再跑本脚本。
ssh 10.32.39.132 "bash ~/cpq/update.sh" || (echo 连接失败:检查本机网络/服务器是否在线。若服务器整机刚重启,等1分钟看门狗自动拉起后再试 & pause & exit /b 1)

echo.
echo 完成! http://10.32.39.132:5173
pause
