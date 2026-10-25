# provider-settings 规格AI 服务商与偏好设置

## Purpose

管理 OpenAI 兼容的 AI 服务商配置（批改能力的后端）与学习偏好参数；所有配置仅保存在本地数据库。

## Requirements

### Requirement: 服务商管理

用户 SHALL 可添加、编辑、删除多个 AI 服务商，每家包含名称、Base URL、API Key、模型名；名称 SHALL 唯一。删除默认服务商时系统 SHALL 自动指定剩余中的第一家为默认。

#### Scenario: 快速填充预设

- **WHEN** 用户在添加表单点击「DeepSeek」或「智谱 GLM」预设按钮
- **THEN** Base URL 与模型名自动填充（https://api.deepseek.com + deepseek-chat；https://open.bigmodel.cn/api/paas/v4 + glm-4.6），API Key 由用户自行填写

### Requirement: Base URL 兼容多种写法

客户端 SHALL 把常见 Base URL 写法规整为完整 chat/completions 地址：裸域名（如 https://api.deepseek.com）追加 `/v1/chat/completions`；版本路径结尾（/v1、/v4 等，如智谱 `/api/paas/v4`、OpenCode Zen `/zen/go/v1`）追加 `/chat/completions`；完整路径原样使用。

#### Scenario: 智谱 v4 地址不拼错

- **WHEN** 用户配置 Base URL 为 https://open.bigmodel.cn/api/paas/v4
- **THEN** 实际请求地址为 https://open.bigmodel.cn/api/paas/v4/chat/completions

### Requirement: 连通性测试

每个服务商 SHALL 提供「测试」按钮，发送极小请求（max_tokens 512）验证连通并显示模型响应摘要；失败时 SHALL 显示可操作的错误原因（如模型名错误、思考型模型配额不足、HTTP 状态码）。

#### Scenario: Key 无效时的提示

- **WHEN** 用户使用错误 API Key 点击测试
- **THEN** 显示失败及服务商返回的错误摘要，而不是空内容成功

### Requirement: Key 安全展示

API Key SHALL 仅保存在本地 SQLite；接口与界面 SHALL 只返回掩码（前 4 位 + **** + 后 4 位）；编辑时留空或保持掩码 SHALL 保留旧 Key。

#### Scenario: 编辑不破坏旧 Key

- **WHEN** 用户编辑服务商但 API Key 输入框保持掩码值
- **THEN** 保存后数据库中仍为原 Key

### Requirement: 思考模式差异化处理

对智谱直连（bigmodel.cn）的 glm-4.x 模型，请求 SHALL 附加 `thinking: {"type": "disabled"}`；对 glm-5.x 系列（强制思考、传 disabled 会 400）SHALL 不附加任何思考参数；其他服务商 SHALL 不附加额外参数，避免网关拒绝未知字段。

#### Scenario: glm-4.6 自动关思考

- **WHEN** 使用智谱直连 glm-4.6 批改
- **THEN** 请求体包含 thinking disabled，避免思维链耗尽输出配额

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
