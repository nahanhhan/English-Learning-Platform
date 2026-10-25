# 提案：背单词/背短语改为选择题模式并引入错题本

## Why（为什么改）

当前学习流是「翻卡自评」（认识/模糊/不认识），自评主观、无强制回忆检验，错了也没有沉淀机制。用户希望：

1. 学习以**四选一选择题**进行，选完立即反馈（错误时绿色标出正确答案、红色标出所选错误项）；
2. 单词在选择后**立即拼写**该词，拼写错误计入错题；
3. 引入**错题本**：答错进入，连续答对 3 次及以上自动移出；
4. 背短语同样改为选择题 + 错题本（无拼写环节）。

## What Changes（变更内容）

- **学习流重做（frontend `Study.tsx`）**：单词卡片流程改为 选择题 → 即时反馈 → 拼写（首字母提示，错误需重打正确一次）；短语流程为 选择题 → 即时反馈；替换原翻卡自评 UI。
- **评分自动化（backend `study.py`）**：SM-2 评分由答题表现自动判定——
  - 单词：选择✓ + 拼写✓ = `good`；选择✓ + 拼写首试✗ = `hard`（计入错题）；选择✗ = `again`（计入错题）
  - 短语：选对 = `good`；选错 = `again`
- **错题本（新增）**：`SrsCard` 增加 `in_mistake_book` / `mistake_consec` 字段（含存量库 ALTER 迁移）；新增错题列表接口与「错题专项练习」队列（source=mistake）；连对 ≥3 自动移出。
- **队列带选项**：学习队列接口为每张卡生成 4 个中文释义选项（1 正确 + 3 同词书干扰项，服务端打乱）。
- 测验 Tab（纯练习不计 SRS）保持不变。

## Impact（影响范围）

- 受影响规格：`vocab-memory`（MODIFIED：SM-2 调度自动化、卡片交互重做；ADDED：选择题答题流程、错题本）
- 代码：`backend/app/models.py`、`backend/app/services/study.py`、`backend/app/routers/vocab.py`、`backend/app/routers/phrases.py`、`frontend/src/pages/Study.tsx`
- 数据：SQLite 存量库需 ALTER TABLE 增列（保留现有学习数据）
- 不变：每日新词配额、到期复习调度、测验 Tab、统计口径
