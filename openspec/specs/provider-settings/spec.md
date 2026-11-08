# provider-settings 规格AI 服务商与偏好设置

## Purpose

管理 Chat Completions 与 Anthropic Messages 的 AI 服务商配置及学习偏好；各服务密钥和模型设置分别保存在本地数据库。

## Requirements

### Requirement: 服务商管理
用户 SHALL 可添加、编辑、删除多条服务模型配置，每条包含名称、Base URL、API Key、模型名、服务类型、推理模式和支持的强度；名称唯一。删除默认配置时自动指定剩余第一条为默认。界面提供 DeepSeek 官方、OpenCode Go 订阅、智谱和自定义兼容服务。

#### Scenario: 快速填充预设
- **WHEN** 用户选择 DeepSeek 官方或 OpenCode Go 订阅预设
- **THEN** 自动填写已核对的独立接口和兼容模型，密钥由用户填写；不将 Go 改成按量接口

### Requirement: Base URL 兼容多种写法

客户端 SHALL 把常见 Base URL 写法规整为完整 chat/completions 地址：裸域名（如 https://api.deepseek.com）追加 `/v1/chat/completions`；版本路径结尾（/v1、/v4 等，如智谱 `/api/paas/v4`、OpenCode Zen `/zen/go/v1`）追加 `/chat/completions`；完整路径原样使用。

#### Scenario: 智谱 v4 地址不拼错

- **WHEN** 用户配置 Base URL 为 https://open.bigmodel.cn/api/paas/v4
- **THEN** 实际请求地址为 https://open.bigmodel.cn/api/paas/v4/chat/completions

### Requirement: 连通性测试
每条配置 SHALL 提供测试，复用正式批改的请求构造及推理设置。普通模型使用小输出配额，推理模型使用足够配额避免只有思考没有正文，截断重试沿用会话。成功显示正文摘要，失败仅显示分类后的可操作原因，不暴露密钥或供应商原始响应。

#### Scenario: Key 无效时的提示
- **WHEN** 用户使用错误密钥点击测试
- **THEN** 显示认证失败，而不是空正文成功或自动换服务

### Requirement: Key 安全展示

API Key SHALL 仅保存在本地 SQLite；接口与界面 SHALL 只返回掩码（前 4 位 + **** + 后 4 位）；编辑时留空或保持掩码 SHALL 保留旧 Key。

#### Scenario: 编辑不破坏旧 Key

- **WHEN** 用户编辑服务商但 API Key 输入框保持掩码值
- **THEN** 保存后数据库中仍为原 Key

### Requirement: 思考模式差异化处理
系统 SHALL 按每条配置与模型能力构造推理参数。可调模型支持默认、开启和关闭，关闭时不发送强度；强制推理的 GLM-5 不发送关闭参数，未知能力使用模型默认。原 GLM-4 配置迁移保持旧有关闭行为，新配置默认跟随模型，用户可以显式选择。

#### Scenario: 保留旧 GLM-4 行为
- **WHEN** 旧数据库迁移且原 GLM-4 配置没有推理字段
- **THEN** 保留服务地址、密钥与默认状态，并将推理模式迁移为关闭

#### Scenario: glm-4.6 自动关思考
- **WHEN** 使用迁移后保持关闭的旧 GLM-4.6 配置，或用户显式选择关闭
- **THEN** 请求包含 thinking disabled，避免思维链耗尽输出配额

### Requirement: 学习偏好

用户 SHALL 可调整每日新学单词/短语上限（1–200，默认 20/10）、模拟批改开关，以及「自动发音」开关（默认开启）。偏好变更 SHALL 立即生效于下一次队列生成、批改请求与学习流卡片切换。

#### Scenario: 调整每日新词量

- **WHEN** 用户把每日新学单词上限改为 30
- **THEN** 下一次进入学习页时当日队列最多出现 30 张新卡（含当日已建卡）

#### Scenario: 开启自动发音

- **WHEN** 用户在设置页打开「自动发音」，随后进入背单词页换到下一张卡
- **THEN** 题面出现时自动播放一次美式发音，无需重启应用

#### Scenario: 关闭自动发音

- **WHEN** 用户在设置页关闭「自动发音」，随后进入背单词页换到下一张卡
- **THEN** 不自动发声；点击「美」按钮仍能正常播放

### Requirement: 推理模式与模型能力
每条服务模型配置 SHALL 保存服务类型、默认或开启或关闭的推理模式及实际支持的强度，提供 DeepSeek 官方和 OpenCode Go 订阅预设、官方说明及模型刷新。未知能力仅使用模型默认，强制推理模型不得关闭，关闭时不发送强度。旧配置和密钥掩码行为保持兼容；各练习共用默认配置且可临时切换。

#### Scenario: 切换推理模式
- **WHEN** 用户将可关闭推理的模型设为关闭
- **THEN** 请求发送对应关闭参数，且不携带推理强度

### Requirement: Go 会话与错误分类
OpenCode Go 的连接测试和正式调用 SHALL 发送真实平台 User-Agent 和每次练习稳定的 x-opencode-session，重试和重译复用，新的独立练习重新生成。不切换到普通按量接口。系统 SHALL 分类显示会话头、认证、额度、参数、超时及格式错误，错误不暴露密钥。请求头兼容不等同于订阅适用性或额度保证。

#### Scenario: 重试保持会话
- **WHEN** 同一次练习在输出截断或人工重试后再次请求 Go
- **THEN** 使用同一会话标识；新练习使用不同标识

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

### Requirement: 本机 Codex 服务

系统 SHALL 提供本机 Codex 服务和 ChatGPT 登录状态，沿用本机默认模型，不要求 API 密钥。服务 SHALL 仅读取用户配置中的默认模型而不启用外部工具配置，不将凭据写入项目，且 SHALL 支持与原有服务并存。

#### Scenario: 使用已有登录

- **WHEN** 用户选用已通过 ChatGPT 登录的本机 Codex
- **THEN** 批改使用该登录和本机默认模型，不使用其他服务或 API 密钥
