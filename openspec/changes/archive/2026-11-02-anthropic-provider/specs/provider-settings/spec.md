## ADDED Requirements

### Requirement: Anthropic 独立接入与 Claude 调用
系统 SHALL 提供 Anthropic 官方独立预设，使用单独的服务密钥与 Messages 接口，支持模型刷新及每条配置的推理模式和实际支持的强度。系统 SHALL 提取正文而非思考内容，拒绝错误、空白、截断和异常格式，复用既有失败保留和人工重试机制。

#### Scenario: 官方 Claude 配置
- **WHEN** 用户选择 Anthropic 官方并保存 Claude 配置
- **THEN** 请求发送至官方 Messages 接口，按模型将推理开启转换为 adaptive 或传统预算格式，强度映射至 output_config.effort，关闭时不发送强度

### Requirement: Go 的 Messages 模型兼容
系统 SHALL 在 Go 模型目录中保留支持 Messages 的模型，按模型自动选择订阅内部接口；已保存的 OpenAI 格式 Go 地址选择 Claude 时也可使用正确 Messages 接口。密钥、真实平台身份和每次练习稳定会话标识 SHALL 保持一致，不切换官方直连或按量服务。

#### Scenario: 已保存的 Claude 配置可调节
- **WHEN** 已有 Go 配置选择 claude-haiku-5-5
- **THEN** 无需重新创建配置即可显示推理开关和五档强度，连接测试和批改均使用 Go 的 Messages 接口
