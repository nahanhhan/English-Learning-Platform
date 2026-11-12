## ADDED Requirements

### Requirement: Windows 批处理脚本兼容性

安装与启动批处理脚本 SHALL 在 Windows 检出后使用 CRLF 换行，并通过 Windows 命令提示符显示中文状态。缺少运行所需文件或运行失败时 SHALL 保留命令窗口和可读的提示。

#### Scenario: 从其他文件夹调用启动脚本

- **WHEN** 用户从其他工作目录打开已经安装的平台启动脚本
- **THEN** 脚本进入项目目录并启动本地服务

#### Scenario: 运行文件尚未准备

- **WHEN** 用户启动平台时缺少后台程序或前端构建产物
- **THEN** 脚本显示对应的中文提示并指引用户运行安装脚本
