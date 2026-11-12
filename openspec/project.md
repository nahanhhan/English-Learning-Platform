# 项目上下文（Project Context）

## 项目概述

**英语学习平台（个人本地版）**：面向单用户的本地英语学习工具，针对大学英语六级（CET-6）与考研英语（二）的翻译题、作文题做 AI 批改，并提供单词/短语的间隔重复记忆与学习数据统计。无登录系统，数据全部保存在本机。

## 技术栈

- **后端**：Rust + Axum + rusqlite（SQLite，文件 `backend/data/app.db`）+ reqwest（AI 服务调用）。Python 媒体工具按需调用 PyMuPDF、RapidOCR 和自然发音引擎。
- **前端**：React 18 + Vite + TypeScript + Ant Design 5 + ECharts（按需引入、路由级代码分割），构建产物 `frontend/dist` 由 Rust 服务托管
- **课内词汇**：独立分组词库，单词/短语释义选择后拼写，持久化整轮进度和错题本；PDF/Word 预览导入与本地 RapidOCR 扫描识别
- **平时积累**：`/accumulation` 独立词库与数据表，复用课内的页面和训练逻辑。新轮次按正确率 60%、间隔 20%、累计次数 20% 的候选范围相对排名选最多 50 条后打乱题序，独立完成记录在重开后保留。词条、错题、轮次及浏览器草稿彼此隔离，整理笔记按批次一次性增量导入。
- **短句翻译**：`/short-translation` 与 `/api/short-translation` 独立题库、练习版本和复习状态；30 道原创模拟题按稳定编号增量导入，草稿留在浏览器。北京时间跨日巩固，模拟批改与即时修改不计次。
- **AI**：支持本机 ChatGPT 登录的 Codex CLI（临时只读运行、三分钟超时、可选模型和推理强度）；兼容 Chat Completions 和 Anthropic Messages（Anthropic 官方 / DeepSeek 官方 / OpenCode Go 订阅 / 智谱 / 自定义），每条服务模型配置分别保存推理模式与支持的强度，各练习可临时选择；密钥仅本地保存、接口掩码返回。Go 的 Claude 自动匹配订阅内部 Messages 接口，使用真实平台身份和每次独立练习稳定的会话头，不转官方直连或按量接口；订阅适用范围与可用额度单独核对。

## 目录结构

```
backend/
  Cargo.toml         # Rust 后端构建入口
  src/               # 本机服务（127.0.0.1:8930）、数据库、学习和批改逻辑
  tools/media.py     # 按需处理文件预览、OCR 与自然发音
  app/               # Python 离线工具、媒体引擎与原版服务
  scripts/           # PDF 抽题、词库制作和资料维护
  data/              # SQLite、题库 JSON、ECDICT CSV、图表图片（charts/）
  tests/             # pytest 单元测试
frontend/
  src/pages/         # Dashboard / Practice / Study(单词与短语共用) / Settings
  src/components/    # GradingResult、TrendChart
六级/、考研英语二/      # 原始真题 PDF（只读资料，平台从这里抽取题目）
setup.bat / start.bat # 一键安装 / 启动
```

## 关键约定

- **语言**：界面、用户可见文案和代码注释使用中文。批改提示要求结构化 JSON，服务端校验结果。
- **评分标准**：六级翻译/作文 15 分制、考研英译汉 15 分制、考研小作文 10 分制、考研大作文 15 分制。六级真题和短句共用 `backend/src/policies.json` 的公开考纲规则与五档描述，先整体定档，可选表达不扣分，维度仅为学习诊断。要求提供评分依据的真实批改保存依据和规则版本。规则修改同步 `openspec/specs/`，历史结果以原记录为准。来源见 `docs/writing-scoring-sources.md`。
- **思考型模型适配**：glm-5.x 强制思考且思维链与正文共享 max_tokens 配额，输出配额为 32000，并由 Rust AI 客户端处理截断后的配额翻倍重试。需要兼容的百分制翻译评分折算回满分制。
- **词库来源**：ECDICT（MIT License）。词书按 tag 筛选：cet6 → 六级书，ky → 考研书；短语 = 内置核心短语 + ECDICT 高频多词词条。
- **数据重建**：`scripts/seed.py --force` 可重建题库与词库；`backend/data/` 删除即彻底清空用户数据。
- **测试**：后端改动检查发布构建并通过本机接口验收；前端改动运行 `npm run build`。验证材料仅保存在本机。

## 常用命令

```bash
# 构建后端
cargo build --locked --release --manifest-path backend/Cargo.toml

# 启动
backend\target\release\english-learning-platform.exe --open-browser     # 或双击 start.bat

# Python 媒体工具与原版回归测试
cd backend && .venv\Scripts\python.exe -m pytest tests/ -q

# 前端构建
cd frontend && npm run build
```
