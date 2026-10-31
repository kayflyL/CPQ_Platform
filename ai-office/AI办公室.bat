@echo off
chcp 936 >nul
echo ==========================================
echo AI 办公室 独立启动
echo ==========================================
echo.
call "%~dp0..\start_core.bat"
echo 打开 AI 办公室...
start "" http://localhost:5173/office/
echo.
echo ==========================================
echo 启动完成！请保持黑色窗口开着
echo ==========================================
pause
