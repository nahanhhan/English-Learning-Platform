# Why

Go 中的 Claude 使用 Messages 接口，当前仅实现 Chat Completions 导致模型能力未知、推理选项无法调节。用户要求增加 Anthropic 独立入口，同时补齐 Go 的 Claude 支持。

# What Changes

- 新增 Anthropic 官方预设、独立密钥配置和模型刷新。
- 实现 Messages 请求与正文解析、推理参数转换及截断重试，连接测试与批改共用。
- Go 按模型自动选择订阅内部接口，保留同一密钥与稳定会话；刷新同时包含 Messages 模型。
- 按官方模型能力显示推理开关和强度，未知模型保持默认，旧配置及学习数据保持不变。

# Capabilities

## Modified Capabilities
- `provider-settings`: Anthropic 预设、Claude 推理与 Go 多接口适配。

# Impact

设置页面、AI 客户端、模型目录及测试；不增加数据库字段，不自动覆盖用户设置，不调用真实订阅进行验证。
