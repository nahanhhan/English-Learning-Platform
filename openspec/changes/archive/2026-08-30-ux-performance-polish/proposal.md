# 提案：交互体验与性能优化批次

## Why（为什么改）

平台主体功能完备后的一轮打磨：减少作答丢失风险、降低操作成本、提升首屏与大数据量接口的性能，并补齐健壮性（渲染异常兜底）。

## What Changes（变更内容）

**行为变更（进规格）**
1. **作答草稿自动保存**：翻译/写作的作答内容实时存入 localStorage（按题目区分，自由练习单独存），重新进入自动恢复，提交成功后清除——防止误关页面丢稿。
2. **快捷提交**：作答框支持 Ctrl+Enter 提交批改。
3. **批改结果自动滚动**：批改完成后页面平滑滚动到结果区。
4. **题目练习次数标注**：题目列表接口返回每题已练次数，列表项显示「已练 n」标签。

**非行为改进（不进规格）**
5. ECharts 改为路由内懒加载（仪表盘统计卡先渲染，图表库异步到位）。
6. 后端干扰项词池（5407 行查询）加 5 分钟内存缓存。
7. 全局 ErrorBoundary、仪表盘加载骨架 Spin、页面标题随路由变化、favicon。

## Impact（影响范围）

- 受影响规格：`practice-grading`（ADDED：草稿自动保存、快捷提交与自动滚动）、`question-bank`（ADDED：练习次数标注）
- 代码：`frontend/src/pages/Practice.tsx`、`frontend/src/pages/Dashboard.tsx`、`frontend/src/App.tsx`、`frontend/src/main.tsx`、`frontend/index.html`、`backend/app/routers/questions.py`、`backend/app/services/study.py`
- 风险控制：全部为增量修改；localStorage 读写失败静默降级；缓存带 TTL 不影响正确性
