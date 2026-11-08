import { Alert } from 'antd'
import { useEffect, useState } from 'react'

export default function GradingProgress({ startedAt }: { startedAt?: string }) {
  const [started] = useState(() => {
    const parsed = startedAt ? Date.parse(startedAt.replace(' ', 'T')) : NaN
    return Number.isFinite(parsed) ? parsed : Date.now()
  })
  const [seconds, setSeconds] = useState(() => Math.max(0, Math.floor((Date.now() - started) / 1000)))
  useEffect(() => {
    const timer = setInterval(() => setSeconds(Math.max(0, Math.floor((Date.now() - started) / 1000))), 1000)
    return () => clearInterval(timer)
  }, [started])
  return <Alert style={{ marginTop: 12 }} type="info" showIcon message={`AI 正在批改，已等待 ${seconds} 秒；作答已保存。`} />
}
