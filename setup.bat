@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || goto :failed
echo 正在准备英语学习平台...
where cargo >nul 2>nul
if errorlevel 1 goto :missing_rust
if exist "backend\.venv\Scripts\python.exe" goto :install_packages
python -m venv "backend\.venv"
if errorlevel 1 goto :failed

:install_packages
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto :failed
pushd "frontend" || goto :failed
call npm ci
if errorlevel 1 goto :frontend_failed
call npm run build
if errorlevel 1 goto :frontend_failed
popd
cargo build --locked --release --manifest-path "backend\Cargo.toml" --target-dir "backend\target"
if errorlevel 1 goto :failed
echo 准备完成。双击 start.bat 启动。
pause
exit /b 0

:missing_rust
echo 请先安装 Rust 工具链，再运行 setup.bat。
goto :failed

:frontend_failed
popd

:failed
echo 准备失败，请保留上方错误信息以便排查。
pause
exit /b 1
