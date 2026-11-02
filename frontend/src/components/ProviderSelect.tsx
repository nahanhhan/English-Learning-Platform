import { Select, Space, Tag } from 'antd'
import { useEffect, useState } from 'react'
import { get } from '../api'

export interface ModelCapability { modes: string[]; levels: string[]; note: string; control: string }
export interface ProviderProfile {
  id: number; name: string; base_url: string; model: string; api_key_masked: string; is_default: boolean
  service_type: string; reasoning_mode: string; reasoning_effort: string
  capabilities: ModelCapability; models: { id: string; name?: string }[]
}
export const MODE_LABELS: Record<string, string> = { auto: '模型默认', enabled: '开启推理', disabled: '关闭推理' }
export const EFFORT_LABELS: Record<string, string> = { minimal: '最低', low: '低', medium: '中', high: '高', xhigh: '更高', max: '最高', ultra: '极高' }

export default function ProviderSelect({ value, onChange, disabled }: {
  value?: number; onChange: (id?: number) => void; disabled?: boolean
}) {
  const [providers, setProviders] = useState<ProviderProfile[]>([])
  useEffect(() => {
    let alive = true
    get('/api/settings').then(data => { if (alive) setProviders(data.providers) }).catch(() => {})
    return () => { alive = false }
  }, [])
  const defaultProvider = providers.find(p => p.is_default) || providers[0]
  const current = value ? providers.find(p => p.id === value) : defaultProvider
  return <Space direction="vertical" size={4} style={{ width: 320, maxWidth: '100%' }}>
    <Select aria-label="AI批改配置" style={{ width: '100%' }} value={value || 0}
      disabled={disabled} onChange={id => onChange(id || undefined)} options={[
        { value: 0, label: defaultProvider ? `全局默认：${defaultProvider.name} · ${defaultProvider.model}` : '全局默认（尚未配置）' },
        ...providers.map(p => ({ value: p.id, label: `${p.name} · ${p.model}` })),
      ]} />
    {current && <span style={{ fontSize: 12, color: '#778396' }}>
      <Tag>{MODE_LABELS[current.reasoning_mode] || '模型默认'}</Tag>
      {current.reasoning_effort && `强度：${EFFORT_LABELS[current.reasoning_effort] || current.reasoning_effort}`}
    </span>}
  </Space>
}
