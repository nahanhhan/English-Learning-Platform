@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || goto :bad_directory
echo 正在启动英语学习平台...
if not exist "backend\target\release\english-learning-platform.exe" goto :missing_runtime
if not exist "frontend\dist\index.html" goto :missing_frontend
"backend\target\release\english-learning-platform.exe" --open-browser
set "startup_exit=%errorlevel%"
if not "%startup_exit%"=="0" echo 启动失败，请保留上方错误信息以便排查。
goto :finish

:bad_directory
echo 无法进入项目文件夹。
goto :failed

:missing_runtime
echo 尚未安装运行环境，请先运行 setup.bat。
goto :failed

:missing_frontend
echo 尚未构建网页，请先运行 setup.bat。

:failed
set "startup_exit=1"

:finish
pause
exit /b %startup_exit%
