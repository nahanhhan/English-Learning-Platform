## ADDED Requirements

### Requirement: 本机 Codex 服务

系统 SHALL 提供本机 Codex 服务和 ChatGPT 登录状态，沿用本机默认模型，不要求 API 密钥。服务 SHALL 仅读取用户配置中的默认模型而不启用外部工具配置，不将凭据写入项目，且 SHALL 支持与原有服务并存。

#### Scenario: 使用已有登录

- **WHEN** 用户选用已通过 ChatGPT 登录的本机 Codex
- **THEN** 批改使用该登录和本机默认模型，不使用其他服务或 API 密钥
