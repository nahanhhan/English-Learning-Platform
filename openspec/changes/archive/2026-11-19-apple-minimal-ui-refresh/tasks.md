# Apple 现代简约风 UI 改版任务清单

- [x] 创建 OpenSpec 变更并校验规格完整性
- [x] 安装并本地打包 `@fontsource-variable/google-sans-flex` 与 `@fontsource-variable/noto-sans-sc`，核对 `@font-face` 实际字体族名并更新 `index.html` 图标
- [x] 重构 `appearance.ts`、`global.css` 与 `workspace.css`（浅/深双主题变量、AntD 主题、`--ease-apple-out`/`--ease-spring`/`--ease-spring-soft` 动效与 `prefers-reduced-motion` 适配）
- [x] 封装统一 `AppIcon` 组件并将全站 `@ant-design/icons` 替换为 `lucide-react`
- [x] 更新全局框架、可持久化侧栏折叠（`Ctrl/⌘+\`）、弹性高亮滑块与毛玻璃 Spotlight（`Ctrl/⌘+K`）
- [x] 精修学习概览、词库练习 4 页、翻译写作与批改报告 3 页、以及设置页共 9 个页面
- [x] 完成类型检查、生产构建与本机浏览器双模式视觉及交互验收
- [x] 归档 OpenSpec 变更并推送到 GitHub `main`
