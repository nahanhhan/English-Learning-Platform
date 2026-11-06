## ADDED Requirements

### Requirement: 第三单元 How we listen 照片词汇

系统 SHALL 将第三单元《How we listen》第 30–37 页的生词和短语作为独立批次加入同名课内分组。`work of art` SHALL 作为短语，`-tempered` SHALL 保留教材写法，专有名称栏 SHALL NOT 纳入。各单词 SHALL 提供词性与美式音标。导入 SHALL 保留已有词条及其学习记录，批次完成后不得因重复启动而覆盖编辑或补回用户删除项。

#### Scenario: 从既有词库升级
- **WHEN** 首批课内课文已导入并存在学习进度
- **THEN** 增量加入第三单元的 55 条生词栏词条和 10 条短语，原记录保持不变

#### Scenario: 再次启动
- **WHEN** 用户编辑或删除本批词条后重启
- **THEN** 不重复导入，也不覆盖既有修改
