@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在准备英语学习平台...
if not exist backend\.venv\Scripts\python.exe (
    python -m venv backend\.venv
    if errorlevel 1 goto failed
)
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 goto failed
pushd frontend
call npm ci
if errorlevel 1 (
    popd
    goto failed
)
call npm run build
if errorlevel 1 (
    popd
    goto failed
)
popd
echo 准备完成。双击 start.bat 启动。
pause
exit /b 0
:failed
echo 准备失败，请保留上方错误信息以便排查。
pause
exit /b 1
