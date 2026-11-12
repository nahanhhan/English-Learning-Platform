# 修复 Windows 启动和安装脚本

## Why

启动和安装脚本在检出时使用了 Linux 换行。Windows 命令提示符读取脚本时会误解析部分中文提示和条件判断，导致平台无法启动。

## What Changes

- 将 Windows 批处理脚本的检出换行统一为 CRLF。
- 保留清楚的中文状态提示，并在安装或启动失败时停留在命令窗口显示原因。

## Capabilities

### Modified Capabilities

- `local-workspace` 增加 Windows 脚本兼容和启动失败反馈约定。

## Impact

Windows 安装脚本、启动脚本及 Git 换行配置。
