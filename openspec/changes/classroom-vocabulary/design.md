# 课内词汇实现设计

## 数据隔离与会话

新增 classroom_groups、classroom_entries、classroom_sessions、classroom_session_items 四表。词条维护错题标记、连续全对次数及完成次数；会话以分组、类型、来源构成唯一范围。题目保存词条快照与选项，支持 choice → spell → done，显式 next 推进。SQLite 自增主键禁止删除后复用，避免旧请求命中新题。

`/api/classroom/sessions/current` 只读取已有轮次；创建或重新开始使用 POST。答题提交包含题目 ID、会话版本和请求编号，事务内条件更新版本取得写锁，再执行错题与阶段修改。已处理编号重试返回当前进度，过期版本返回 409。取消、重开、切换范围会使前端过期响应失效。

## 文件导入

使用原始二进制请求体，不引入 multipart 依赖；上传仅在内存中提取，不写静态目录。PDF 采用 PyMuPDF，缺失或明显损坏文本层及只有图片文字的页面转本地 RapidOCR。Word 使用标准库读取 OOXML 正文和表格。所有来源统一转换为可编辑条目和完整提取原文，确认时事务写入；唯一键为分组、类型、规范化英文。

## 首批资料

照片原件不复制入项目。整理结果存储于 classroom_initial.json，保留课文、页码和筛选说明。以 user_settings 中的版本标记保证一次性初始化。临时验证通过 ENGLISH_PLATFORM_DATA_DIR 使用独立数据库，既有学习库在实际增量建表前使用 SQLite backup 备份。
