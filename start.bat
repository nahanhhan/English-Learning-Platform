@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动英语学习平台...
if not exist backend\target\release\english-learning-platform.exe (
    echo 尚未安装运行环境，请先运行 setup.bat。
    pause
    exit /b 1
)
if not exist frontend\dist\index.html (
    echo 尚未构建网页，请先运行 setup.bat。
    pause
    exit /b 1
)
backend\target\release\english-learning-platform.exe --open-browser
pause
