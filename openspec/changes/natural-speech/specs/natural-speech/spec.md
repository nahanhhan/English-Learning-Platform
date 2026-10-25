## ADDED Requirements

### Requirement: 完整自然语音

系统 SHALL 提供 `POST /api/speech`，接收原始英文 `text` 与口音 `accent`（`us` 或 `uk`，默认 `us`），返回完整 `audio/mpeg`。美式 SHALL 固定使用 `en-US-JennyNeural`，英式 SHALL 固定使用 `en-GB-SoniaNeural`，语速 SHALL 为 `-5%`，音高 SHALL 为 `+0Hz`。每个词条 SHALL 整体通过 edge-tts 生成，SHALL NOT 拼接逐词词典录音或切换电脑语音。

#### Scenario: 同声线朗读单词与短语

- **WHEN** 用户分别播放一个单词和含多个单词的短语的美式发音
- **THEN** 两者均使用 Jenny，短语作为完整文本生成，英式按钮仍使用 Sonia

### Requirement: 仅规范朗读文本

后端 SHALL 在生成前将完整占位词 `sb`、`sth`（忽略大小写和可选句点）展开为 `somebody`、`something`，保留所有格；将带空格或不带空格的 `/` 展开为 `or`，移除括号符号并保留括号内文字。SHALL NOT 更改页面文本、词库内容、拼写答案或其他英文单词。

#### Scenario: 缩写与所有格

- **WHEN** 输入 `do sth.`、`stand SB up`、`sb.'s`、`sb/sth`
- **THEN** 朗读文本分别为 `do something`、`stand somebody up`、`somebody's`、`somebody or something`

#### Scenario: 括号与完整词

- **WHEN** 输入 `have / get a shot at (doing) sth`、`splash` 或 `substance`
- **THEN** 首项按 `have or get a shot at doing something` 朗读，后两项保持原样

### Requirement: 持久完整音频缓存

系统 SHALL 按规范后的文本、声音、语速、音高和规则版本生成缓存键，将完整 MP3 原子保存于本地数据目录的 `speech-cache`。同一进程内相同内容的并发请求 SHALL 合并；单个请求取消 SHALL NOT 取消其他等待者。生成失败、超时或未完整结束的流 SHALL NOT 入缓存，后续可重试。已有缓存 SHALL 无需联网即可跨重启使用。SHALL NOT 修改数据库结构或学习记录。

#### Scenario: 重启与断网命中

- **WHEN** 已生成的词条在重启后、网络不可用时再次请求
- **THEN** 直接返回相同本地 MP3，不请求在线服务

#### Scenario: 失败后重试

- **WHEN** 生成流中断或超时
- **THEN** 返回可重试的错误，不留下半成品缓存；重试可重新完整生成

### Requirement: 统一可取消播放

所有学习、错题专项、测验、词表及设置页试听 SHALL 复用该接口。新发音、切题或离开页面 SHALL 中止旧请求和播放，拒绝迟到响应并释放临时音频地址；同一题进入拼写时 SHALL 取消尚未开始的请求，已开始的发音可自然读完。SHALL 保留自动发音开关、当前浏览器音量记忆及静音，音量改变 SHALL 作用于当前播放。生成失败 SHALL 仅显示轻量重试入口，SHALL NOT 自动换声或阻塞答题。

#### Scenario: 快速切题或离开

- **WHEN** 请求尚未返回时用户切题、切换入口或重新点击发音
- **THEN** 旧请求被取消，旧响应不得播放，最多保留当前一次播放

#### Scenario: 自动发音和静音

- **WHEN** 自动发音关闭或当前音量为零
- **THEN** 分别不自动朗读或不发出任何发音，恢复音量不会补播旧音频

#### Scenario: 无缓存且在线失败

- **WHEN** 用户播放未缓存词条但在线生成失败
- **THEN** 显示重试提示，答题照常继续，不调用浏览器语音或词典录音
