## MODIFIED Requirements

### Requirement: 服务商管理
用户 SHALL 可添加、编辑、删除多条服务模型配置，每条包含名称、Base URL、API Key、模型名、服务类型、推理模式和支持的强度；名称唯一。删除默认配置时自动指定剩余第一条为默认。界面提供 DeepSeek 官方、OpenCode Go 订阅、Anthropic 官方、Google Gemini 官方、智谱和自定义兼容服务。

#### Scenario: 快速填充预设
- **WHEN** 用户选择 DeepSeek 官方、OpenCode Go 订阅或 Google Gemini 官方预设
- **THEN** 自动填写已核对的独立接口和兼容模型，密钥由用户填写；不将 Go 改成按量接口

### Requirement: Base URL 兼容多种写法

客户端 SHALL 把常见 Base URL 写法规整为完整 chat/completions 地址：裸域名（如 https://api.deepseek.com）追加 `/v1/chat/completions`；版本路径结尾（/v1、/v4 等，如智谱 `/api/paas/v4`、OpenCode Zen `/zen/go/v1`）以及版本加 `/openai` 结尾（如 Gemini `/v1beta/openai`）追加 `/chat/completions`；完整路径原样使用。

#### Scenario: Gemini OpenAI 兼容地址不误拼 v1

- **WHEN** 用户配置 Base URL 为 https://generativelanguage.googleapis.com/v1beta/openai
- **THEN** 实际请求地址为 https://generativelanguage.googleapis.com/v1beta/openai/chat/completions

## ADDED Requirements

### Requirement: Google Gemini 官方接入
系统 SHALL 提供 Google Gemini 官方预设，使用 Google AI Studio 颁发的 `GEMINI_API_KEY` 通过官方 OpenAI 兼容接口（`https://generativelanguage.googleapis.com/v1beta/openai`）发起请求，校验官方主机与路径，支持已声明模型的推理强度（`reasoning_effort`）调节以及在线模型列表刷新（去除返回模型标识中的 `models/` 前缀）。未知能力的模型保持默认设置。

#### Scenario: 刷新 Gemini 模型目录并调用
- **WHEN** 用户选择 Google Gemini 官方预设并刷新模型列表或发起批改
- **THEN** 从官方 OpenAI 兼容模型接口获取目录并去掉 `models/` 前缀，请求使用所选模型与推理强度发送至官方 `/v1beta/openai/chat/completions`
