import React, { useLayoutEffect, useMemo, useState, useSyncExternalStore } from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { appearanceKey, readAppearance, workspaceTheme } from './appearance'
import ErrorBoundary from './ErrorBoundary'
import './global.css'
import './workspace.css'

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

function subscribeToMotion(onChange: () => void) {
  reducedMotion.addEventListener('change', onChange)
  return () => reducedMotion.removeEventListener('change', onChange)
}

function Root() {
  const motion = useSyncExternalStore(subscribeToMotion, () => !reducedMotion.matches)
  const [appearance, setAppearance] = useState(readAppearance)
  const config = useMemo(() => workspaceTheme(appearance, motion), [appearance, motion])

  useLayoutEffect(() => {
    document.documentElement.dataset.appearance = appearance
    ConfigProvider.config({ holderRender: children => <ConfigProvider theme={config}>{children}</ConfigProvider> })
    try {
      localStorage.setItem(appearanceKey, appearance)
    } catch {
      // 本地存储不可用时，当前页面仍可切换外观。
    }
  }, [appearance, config])

  return (
    <ConfigProvider locale={zhCN} theme={config}>
      <BrowserRouter>
        <ErrorBoundary>
          <App appearance={appearance} onAppearanceChange={() => {
            setAppearance(current => current === 'dark' ? 'light' : 'dark')
          }} />
        </ErrorBoundary>
      </BrowserRouter>
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
