@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动英语学习平台...
start "" http://127.0.0.1:8930
backend\.venv\Scripts\python.exe backend\main.py
pause
