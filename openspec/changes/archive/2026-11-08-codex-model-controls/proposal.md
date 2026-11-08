# 提案：调整 Codex 模型和推理强度

## Why

现有英语平台只能沿用本机 Codex 的默认模型及强度，用户无法针对批改任务调整模型选择和思考深度，也不能直观看到当前设置。

## What Changes

- 设置页提供 Codex 模型和推理强度选择，允许恢复默认。
- 模型与强度取自本机 Codex 模型目录，目录缺失时允许手动输入并标明需测试。
- 保存后的设置仅用于平台批改，并保留已有服务、记录和账号登录。

## Capabilities

### Modified Capabilities

- `provider-settings`: Codex 模型和推理强度设置。
