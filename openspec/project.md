# 项目上下文（Project Context）

## 项目概述

**英语学习平台（个人本地版）**：面向单用户的本地英语学习工具，针对大学英语六级（CET-6）与考研英语（二）的翻译题、作文题做 AI 批改，并提供单词/短语的间隔重复记忆与学习数据统计。无登录系统，数据全部保存在本机。

## 技术栈

- **后端**：Python 3.11 + FastAPI + SQLAlchemy 2.0（SQLite，文件 `backend/data/app.db`）+ httpx（OpenAI 兼容 AI 调用）+ PyMuPDF / RapidOCR（真题 PDF 抽取）
- **前端**：React 18 + Vite + TypeScript + Ant Design 5 + ECharts（按需引入、路由级代码分割），构建产物 `frontend/dist` 由 FastAPI 托管
- **课内词汇**：独立分组词库，单词/短语释义选择后拼写，持久化整轮进度和错题本；PDF/Word 预览导入与本地 RapidOCR 扫描识别
- **平时积累**：`/accumulation` 独立词库与数据表，复用课内的页面、训练服务和接口工厂，词条、错题、轮次及浏览器草稿彼此隔离；整理笔记一次性导入。
- **短句翻译**：`/short-translation` 与 `/api/short-translation` 独立题库、练习版本和复习状态；30 道原创模拟题按稳定编号增量导入，草稿留在浏览器。北京时间跨日巩固，模拟批改与即时修改不计次。
- **AI**：兼容 Chat Completions 服务（DeepSeek 官方 / OpenCode Go 订阅 / 智谱 / 自定义），每条服务模型配置分别保存推理模式与支持的强度，各练习可临时选择；密钥仅本地保存、接口掩码返回。Go 使用真实平台身份和每次独立练习稳定的会话头，不转按量接口；订阅适用范围与可用额度单独核对。

## 目录结构

```
backend/
  main.py            # 启动入口（127.0.0.1:8930），托管前端与 /data-static 静态资源
  app/
    models.py        # 全部 ORM 模型
    routers/         # questions / practice / vocab / phrases / stats / settings
    services/        # ai_client（OpenAI 兼容客户端）、grading（评分 Prompt 与校验）、srs（SM-2）、study（学习队列）
  scripts/           # extract_questions.py（PDF 抽题）、import_ecdict.py（词库）、seed.py（初始化）
  data/              # SQLite、题库 JSON、ECDICT CSV、图表图片（charts/）
  tests/             # pytest 单元测试
frontend/
  src/pages/         # Dashboard / Practice / Study(单词与短语共用) / Settings
  src/components/    # GradingResult、TrendChart
六级/、考研英语二/      # 原始真题 PDF（只读资料，平台从这里抽取题目）
setup.bat / start.bat # 一键安装 / 启动
```

## 关键约定

- **语言**：界面与用户可见文案全部中文；代码注释用中文；Prompt 输出要求结构化 JSON 并用 Pydantic 式校验兜底。
- **评分标准**：六级翻译/作文 15 分制、考研英译汉 15 分制、考研小作文 10 分制、考研大作文 15 分制；官方分档描述内置于 `backend/app/services/grading.py`，修改评分逻辑必须同步该文件与 `openspec/specs/`。
- **思考型模型适配**：glm-5.x 强制思考且思维链与正文共享 max_tokens 配额——不要对其发送 `thinking: disabled`（会 400），输出配额需放大（当前 32000）并依赖 `ai_client.chat` 的配额翻倍重试；百分制分数需折算回满分制。
- **词库来源**：ECDICT（MIT License）。词书按 tag 筛选：cet6 → 六级书，ky → 考研书；短语 = 内置核心短语 + ECDICT 高频多词词条。
- **数据重建**：`scripts/seed.py --force` 可重建题库与词库；`backend/data/` 删除即彻底清空用户数据。
- **测试**：后端改动跑 `python -m pytest tests/ -q`；前端改动跑 `npm run build` 确认类型与构建通过。

## 常用命令

```bash
# 启动
backend\.venv\Scripts\python.exe backend\main.py     # 或双击 start.bat

# 后端测试
cd backend && .venv\Scripts\python.exe -m pytest tests/ -q

# 前端构建
cd frontend && npm run build
```
