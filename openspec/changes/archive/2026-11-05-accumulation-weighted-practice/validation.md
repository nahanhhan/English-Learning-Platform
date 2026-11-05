# 验证记录

## 功能与数据

- 实施前本地与云端同为 `251d97fa44d832437126a330147a549de938c6a2`，工作区干净。
- 选题仅针对积累板块，以候选范围平均百分位排名计算 60% 正确率、20% 间隔时长、20% 累计次数，取前 50 条后打乱展示。正确率使用 80% 最近 10 次加 20% 更新后全部完整作答表现。
- 独立完成记录以题目编号唯一；选择和首次拼写均正确才算全对。重开不删除，纠正、重试与下一题不增加重复样本。旧次数保留，旧正确率与日期未知时不回填。
- 新增表由现有启动建表流程自动创建；旧表无需改列。升级测试比较所有既有表逐行数据，重复启动后完全保留。
- 页面显示最近全对率、原累计次数和北京时间的最新完成时间，不显示建议日期。接口扩展为可选 `recent_accuracy`、`recent_attempts`、`last_practiced_at`；课内接口不增加这些统计字段。

## 检查结果

- 后端完整测试：248 项通过。覆盖三项独立方向与精确权重、并列平均秩、未知中性与旧错题信号、候选全范围及筛选、最近十次与累计记录、相同时间的顺序、独立记录幂等与事务回滚、重开保留、删除隔离、旧表升级及旧轮次音标补齐。
- 前端构建通过。
- 隔离浏览器与临时数据库中检查权重说明、50 题、四个单词音标、统计数据与北京时间、拼写草稿刷新恢复、错后纠正与重新开始后记录保留。课内同样 70 条候选仍练全部 70 条，积累仅选 50 条。
- 页面验证不调用 AI，不修改生产数据库；数据库、密钥、个人配置、依赖及验证截图和临时工具不进入交付文件。

## 美式音标来源

- [benefaction：剑桥词典](https://dictionary.cambridge.org/us/dictionary/english/benefaction?topic=giving-providing-and-supplying)：补充美式 /ˌben.əˈfæk.ʃən/。
- [lamentation：剑桥词典](https://dictionary.cambridge.org/us/dictionary/english/lamentation?topic=sadness-and-regret)：补充美式 /ˌlæm.enˈteɪ.ʃən/。
- [would-be：剑桥词典](https://dictionary.cambridge.org/pronunciation/english/would-be)：补充 /ˈwʊd.bi/。
- `ill-reputed` 按既有复合词策略分别查询本地 CMU 的 `ill` 和 `reputed`，不改词条拼写，不调用在线接口猜音。其第二部分也可核对[剑桥 reputed 的美式读音](https://dictionary.cambridge.org/us/dictionary/english/reputed?topic=seeming-and-purporting-to-be)。
