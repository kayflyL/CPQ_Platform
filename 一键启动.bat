@echo off
chcp 936 >nul
echo ==========================================
echo CPQ Platform 一键启动
echo ==========================================
echo.
call "%~dp0start_core.bat"
echo [3/3] 打开浏览器（CPQ + AI 办公室双开）...
start "" http://localhost:5173
start "" http://localhost:5173/office/
echo.
echo ==========================================
echo 启动完成！请保持黑色窗口开着
echo ==========================================
pause
