# question-bank 规格增量：练习次数标注

## ADDED Requirements

### Requirement: 题目练习次数标注

题目列表 SHALL 返回每道题的已提交练习次数（practice_count，含批改失败与成功的提交）；前端列表项 SHALL 为练习次数大于 0 的题目显示「已练 n」标签，帮助用户识别未练过的真题。

#### Scenario: 识别未练题目

- **WHEN** 用户做过 2025 年 12 月第 1 套翻译并提交过一次
- **THEN** 该题在列表中显示「已练 1」，未做过的题目无此标签
