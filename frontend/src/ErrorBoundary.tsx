import { Button, Result } from 'antd'
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
        <Result
          status="error"
          title="页面出了点问题"
          subTitle={`渲染异常：${this.state.error.message || '未知错误'}`}
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              刷新页面
            </Button>
          }
        />
      )
    }
    return this.props.children
  }
}
