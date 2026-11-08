## ADDED Requirements

### Requirement: Codex 真题与写作批改

系统 SHALL 支持 Codex 按既有评分规则批改翻译和写作，展示等待时间；单次批改及修复 SHALL 在三分钟内完成。失败或结果不完整时 SHALL 保留作答，且 SHALL NOT 自动切换服务或使用模拟成绩。

#### Scenario: 服务失败

- **WHEN** Codex 认证失败或额度不足
- **THEN** 结果标记为失败，显示原因，原作答可用于手动重试

## MODIFIED Requirements

### Requirement: 模拟批改

开启「模拟批改」时，普通服务 SHALL 返回结构完整的示例批改结果并标记 `mock: true`；选用 Codex 时 SHALL 提示先关闭模拟批改，避免误把示例当成真实结果。

#### Scenario: 未配置服务商时的模拟批改

- **WHEN** 未配置任何服务商且未开启模拟批改
- **THEN** 批改失败并提示「尚未配置 AI 服务商」；开启模拟批改后同一提交可立即获得示例结果
