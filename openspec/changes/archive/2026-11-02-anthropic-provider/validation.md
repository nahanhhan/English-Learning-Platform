# 验证记录（2026-11-02）

- 实施前本地与 `origin/main` 一致，基准提交 `414c7c1585c563ca160708da3a604249ac2a41ee`，无未提交项目改动。
- 已核对 [Claude Messages](https://platform.claude.com/docs/en/api/messages/create)、[模型目录](https://platform.claude.com/docs/en/api/models/list)、[思考模式](https://platform.claude.com/docs/en/build-with-claude/thinking)、[强度](https://platform.claude.com/docs/en/build-with-claude/effort)和 [Go 接口](https://opencode.ai/v2/docs/console/go/)。Haiku 5.5 支持五档强度，关闭时省略强度；部分其他 Claude 无法完全关闭，按能力隐藏关闭选项。
- 全部后端测试：`backend/.venv/Scripts/python.exe -m pytest backend/tests -q`，197 passed。覆盖官方和新旧 Go 地址、鉴权及会话保持、系统提示转换、正文与思考隔离、参数映射、截断与超时、响应拒绝或格式异常、目录能力与分页、密钥掩码保存及旧配置兼容。
- 前端 `npm run build` 类型检查和生产构建通过。
- 浏览器使用独立配置、全新临时数据库和模拟传输，复现已有 Go 地址＋Claude Haiku 5.5：推理开关、五档强度、关闭时禁用强度、保存和模拟连接成功。新增 Anthropic 官方入口可独立保存官方虚拟密钥及强度，模拟连接使用官方 Messages 地址。短句首答与重译均获得可显示的结构化反馈，重译保持同一 Go 会话，思考内容未进入批改正文。模型刷新保留 Messages 模型；宽屏、600 和 375 像素窗口截图已检查。
- Tabbit CLI 本机注册不可用，未修改其配置；改用独立无头 Chrome 完成本地验证，不操作用户浏览器。测试脚本、截图、虚拟密钥和临时数据库均不上传。
- 正式本地数据库 21 张表在修改前后逐表核对记录数量与摘要，全部一致，SQLite 完整性为 `ok`；未更改已保存服务、默认状态、密钥和学习记录，不增加字段或迁移数据。
- 未使用真实密钥调用 Anthropic 或 Go。连接、评分和会话验证均为模拟传输；不宣称真实订阅权限、额度或翻译用途可用，实际调用可在设置页手动测试，不自动转到其他服务。
