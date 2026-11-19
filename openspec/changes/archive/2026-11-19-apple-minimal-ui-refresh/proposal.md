# Apple 现代简约风 UI 改版

## Why

当前深灰工作台偏紧凑技术面板风格，图标体系混用了 `@ant-design/icons` 与 `lucide-react`，字体依赖系统回退（Windows 下回退为微软雅黑），页面缺少侧栏折叠、方向键快速跳转和精细的非线性交互反馈。本次改版按已确认的 Apple 现代简约桌面风方案，提供默认浅色与精调 macOS 深色双主题、离线 Google 变量字体、全站统一纤细图标、流畅动效体系及全站 9 页面视觉精修。

## What Changes

- 外观与双主题：默认切换为 Apple 浅色（`#F5F5F7` / `#ECECEF` / `#FFFFFF` / `#007AFF`），同步精调 macOS 深色（`#1C1C1E` / `#161618` / `#2C2C2E` / `#0A84FF`），存储键升级为 `elp-appearance-v2`。
- 离线字体与图标：本地打包 `@fontsource-variable/google-sans-flex` 与 `@fontsource-variable/noto-sans-sc`，基础字号 `14px`、控件高度 `36px`；全站移除 `@ant-design/icons`，统一为 `AppIcon` + `lucide-react` 纤细图标，并更新 `index.html` favicon。
- 导航与动效：新增可持久化侧栏折叠（按钮 + `Ctrl/⌘+\`）与折叠后展开条、侧栏弹性高亮滑块、Spotlight（`Ctrl/⌘+K`）键盘 `↑`/`↓`/`Enter`/`Esc` 毛玻璃弹窗、切页指数减速与卡片错峰入场、分段控制器与弹簧开关物理曲线，并自动适配 `prefers-reduced-motion`。
- 全站 9 页面精修：重构学习概览、背单词/背短语/课内生词和短语/平时单词短语积累、真题翻译/短句翻译/写作练习与 AI 批改报告、以及 macOS「系统设置」风格设置页。

## Capabilities

### Modified Capabilities

- `local-workspace`：更新双主题默认值与存储键、离线字体、统一图标、非线性动效、可折叠侧栏与 Spotlight 键盘交互规格。

## Impact

涉及前端 `frontend/package.json`、`frontend/index.html`、`frontend/src/main.tsx`、`frontend/src/App.tsx`、`frontend/src/appearance.ts`、`frontend/src/global.css`、`frontend/src/workspace.css`、公共组件与全部 9 个路由页面，不改动后端接口或用户学习数据。
