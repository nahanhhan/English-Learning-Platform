import React, { useSyncExternalStore } from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import ErrorBoundary from './ErrorBoundary'
import './global.css'

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

function subscribeToMotion(onChange: () => void) {
  reducedMotion.addEventListener('change', onChange)
  return () => reducedMotion.removeEventListener('change', onChange)
}

function Root() {
  const motion = useSyncExternalStore(subscribeToMotion, () => !reducedMotion.matches)

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#285a96',
          colorText: '#192d42',
          borderRadius: 8,
          fontSize: 14,
          motion,
        },
      }}
    >
      <BrowserRouter>
        <ErrorBoundary>
          <App />
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
