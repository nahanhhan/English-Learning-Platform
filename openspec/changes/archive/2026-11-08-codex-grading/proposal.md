# 提案：使用本机 Codex 批改

## Why

学习平台需要使用用户已登录的 ChatGPT/Codex 账号，完成短句、真题翻译和写作批改，同时保留已有服务、学习记录与评分标准，并在连接失败时明确提示。

## What Changes

- 新增本机 Codex 服务，保持现有服务、评分规则、作答与复习记录。
- 复用本机 ChatGPT 登录和默认模型，失败时保留作答并提示手动切换，不使用模拟结果兜底。
- 临时只读运行并关闭外部应用，限制时间为三分钟；界面显示登录状态与批改等待时间。

## Capabilities

### Modified Capabilities

- `provider-settings`: 本机 Codex 登录与服务选择。
- `practice-grading`: 真题、写作批改与安全失败。
- `short-translation`: 保留重译上下文和记录。
