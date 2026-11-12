import React from 'react'

interface State {
  error: Error | null
}

/** 全局渲染异常兜底：显示友好页面而不是白屏 */
export default class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('页面渲染异常:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="page">
          <section className="panel workspace-error" role="alert">
            <h1 className="page-title">页面暂时无法显示</h1>
            <p>可以刷新后重试，也可以从导航打开其他页面。</p>
            <button className="workspace-menu-button" onClick={() => window.location.reload()}>刷新页面</button>
          </section>
        </div>
      )
    }
    return this.props.children
  }
}
