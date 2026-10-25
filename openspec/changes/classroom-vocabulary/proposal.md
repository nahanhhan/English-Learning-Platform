# 提案：课内生词和短语

## Why

课内词汇需要独立分组、整组复习和断点续练，现有考试词书的每日配额与短语免拼写流程不适用。

## What Changes

- 新增课内词汇入口、课程/单元分组与词表管理。
- 单词、短语统一先选择释义再拼写，错误立即入本，连对三次移出。
- 持久化题目快照、答题阶段和结果；防止重复提交重复计分。
- 支持逐条添加、批量粘贴、PDF/Word 预览导入及扫描 PDF 本地识别。
- 整理用户提供的八张课本照片，幂等导入首批词汇。

## Capabilities

### New Capabilities

- `classroom-vocabulary`: 独立课内词库、复习会话与文件导入。

### Modified Capabilities

- 无。

## Impact

新增四张课内数据表及 `/api/classroom` 接口、`/classroom` 页面；增量建表，不重置既有数据。扫描识别使用 RapidOCR，Word 使用标准库读取 OOXML，不依赖本机 Office。

## Non-goals

不增加每日配额、AI 自动选词、AI 生成释义或旧版 `.doc` 转换。
