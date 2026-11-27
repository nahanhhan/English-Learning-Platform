# Why

用户希望在英语学习平台中合规接入 Google Gemini 模型用于翻译与写作批改，通过 Google AI Studio 申请的 `GEMINI_API_KEY` 直接调用官方 OpenAI 兼容接口，避免手动拼接容易出错的 `/v1beta/openai` 地址，也无需经由个人 OAuth 或外部 CLI 代理。

# What Changes

- 在后端与设置页面新增 `Google Gemini 官方` 预设（`service_type: "gemini"`），默认接入 `https://generativelanguage.googleapis.com/v1beta/openai` 与模型 `gemini-3.5-flash-lite`，并内置当前可用的 Gemini 3.5 / 4 系列模型目录。
- 修复通用与预设 URL 规整规则，支持 `/v1beta/openai` 等 `/vN.../openai` 路径直接拼接 `/chat/completions`，不误追加 `/v1`。
- 支持 Gemini 官方模型的推理强度映射（`reasoning_effort`）及在线模型列表刷新（自动去除兼容接口返回的 `models/` 前缀）。
- 在设置界面增加 AI Studio 密钥、免费层速率与隐私说明及官方跳转链接。

# Capabilities

## Modified Capabilities
- `provider-settings`: 新增 Google Gemini 官方预设、`/openai` 路径规整、模型刷新及推理强度支持。

# Impact

前后端 AI 服务商预设、URL 规整、模型目录、单元测试及 OpenSpec 规格；不改动数据库表结构，不影响已有服务商配置与学习记录。
