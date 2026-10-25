# practice-grading 规格增量：作答体验优化

## ADDED Requirements

### Requirement: 作答草稿自动保存

作答内容 SHALL 实时自动保存到本地（localStorage，按题目 id 区分，自由练习独立保存）；重新进入同一题目时 SHALL 自动恢复未提交的草稿；提交成功后 SHALL 清除对应草稿。本地存储不可用时 SHALL 静默降级，不影响作答与提交流程。

#### Scenario: 误关页面不丢稿

- **WHEN** 用户在某道写作题输入内容后未提交即关闭页面，稍后重新打开该题
- **THEN** 输入框自动恢复之前的作答内容；提交成功后草稿被清除

### Requirement: 快捷提交与结果自动滚动

作答框 SHALL 支持 Ctrl+Enter 快捷提交批改；批改完成时页面 SHALL 平滑滚动到批改结果区，无需手动翻页。

#### Scenario: 快捷键提交

- **WHEN** 用户在作答框内按下 Ctrl+Enter 且内容非空
- **THEN** 等价于点击「提交批改」按钮，进入批改流程
