# Why

用户在 `English_notes.docx` 的第 92 至 102 段新增了 11 个单词词条，需要将它们增量导入平时积累词库，并补全词典缺失单词的美式音标。

# What Changes

- 整理第 92 至 102 段的 11 个单词为独立批次 `backend/data/accumulation_notes_20261123.json`，记录原文段落与整理说明。
- 在 Rust 后端 `backend/src/db.rs` 与 Python 种子脚本 `backend/scripts/seed_accumulation.py` 注册新批次，沿用跨分组去重与一次性导入流程。
- 在 `backend/src/dictionary.rs` 与 `backend/app/services/phonetics.py` 为 CMU 词典缺失的 `underprivileged` 补充经核对的美式音标。
- 更新 `backend/tests/test_accumulation.py` 与 `backend/tests/test_phonetics.py` 覆盖新批次与音标验证。

# Impact

本次更新词库数据、批次列表与离线音标补充，沿用现有 `daily-vocabulary` 规格，保留用户既有词条修改与学习记录。
