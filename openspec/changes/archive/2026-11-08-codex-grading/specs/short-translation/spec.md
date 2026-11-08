## ADDED Requirements

### Requirement: Codex 短句批改

短句练习 SHALL 支持选用本机 Codex，继续携带原有评分规则和上次作答及反馈。失败 SHALL 保留作答而不计学习进度。

#### Scenario: 短句重译

- **WHEN** 学习者使用 Codex 提交修改版
- **THEN** 批改参考上一版作答和反馈，成功后按既有规则记录结果
