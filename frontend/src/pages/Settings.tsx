import {
  ApiOutlined, CheckOutlined, DeleteOutlined, EditOutlined, PlusOutlined,
} from '@ant-design/icons'
import {
  Alert, Button, Card, Empty, Form, Input, InputNumber, Modal, Popconfirm,
  Space, Switch, Tag, Select, AutoComplete, message,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { del, get, post, put } from '../api'
import VolumeControl from '../components/VolumeControl'
import { type ProviderProfile, type ModelCapability, MODE_LABELS, EFFORT_LABELS } from '../components/ProviderSelect'
import { speak, stopSpeaking } from '../speak'

type Provider = ProviderProfile
interface Preset { name: string; service_type: string; base_url: string; model: string; docs: string; models: { id: string; name?: string }[] }

export default function Settings() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [prefs, setPrefs] = useState<any>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const [form] = Form.useForm()
  const [testing, setTesting] = useState<number | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [caps, setCaps] = useState<ModelCapability>({ modes: ['auto'], levels: [], control: 'none', note: '使用模型默认设置' })
  const [refreshing, setRefreshing] = useState(false)
  const [codexStatus, setCodexStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [codexConnection, setCodexConnection] = useState<{ ok: boolean; message: string } | null>(null)
  const formModel = Form.useWatch('model', form)
  const formType = Form.useWatch('service_type', form)
  const formBase = Form.useWatch('base_url', form)
  const formMode = Form.useWatch('reasoning_mode', form)

  const load = useCallback(async () => {
    const data = await get('/api/settings')
    setProviders(data.providers)
    setPrefs(data.prefs)
    const options = await get('/api/settings/provider-options')
    setPresets(options.profiles)
  }, [])

  useEffect(() => { load().catch((e) => message.error(e.message)); get('/api/settings/codex/status').then(setCodexStatus).catch(() => setCodexStatus({ ok: false, message: '无法读取本机 Codex 状态' })) }, [load])
  useEffect(() => () => stopSpeaking(), [])

  useEffect(() => {
    if (!modalOpen) return
    let alive = true
    post<ModelCapability>('/api/settings/provider-capabilities', { provider_id: editing?.id,
      service_type: formType || 'custom', base_url: formBase || '', model: formModel || '' })
      .then(data => {
        if (!alive) return
        setCaps(data)
        if (!data.modes.includes(form.getFieldValue('reasoning_mode') || 'auto')) form.setFieldValue('reasoning_mode', 'auto')
        if (!data.levels.includes(form.getFieldValue('reasoning_effort'))) form.setFieldValue('reasoning_effort', '')
      }).catch(() => { if (alive) setCaps({ modes: ['auto'], levels: [], control: 'none', note: '无法获取能力，请使用模型默认设置' }) })
    return () => { alive = false }
  }, [modalOpen, formModel, formType, formBase, editing, form])

  const openModal = (p?: Provider) => {
    setEditing(p || null)
    form.resetFields()
    if (p) {
      form.setFieldsValue({ name: p.name, base_url: p.base_url, model: p.model, api_key: p.api_key_masked, is_default: p.is_default,
        service_type: p.service_type, reasoning_mode: p.reasoning_mode, reasoning_effort: p.reasoning_effort })
    }
    setModalOpen(true)
  }

  const saveProvider = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        await put(`/api/settings/providers/${editing.id}`, values)
        message.success('已保存')
      } else {
        await post('/api/settings/providers', values)
        message.success('已添加')
      }
      setModalOpen(false)
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const testProvider = async (p: Provider) => {
    setTesting(p.id)
    try {
      const r = await post(`/api/settings/providers/${p.id}/test`)
      if (p.service_type === 'codex') setCodexConnection(r)
      if (r.ok) message.success(r.message)
      else message.error(r.message)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setTesting(null)
    }
  }

  const removeProvider = async (id: number) => {
    await del(`/api/settings/providers/${id}`)
    message.success('已删除')
    load()
  }

  const savePrefs = async (patch: any) => {
    await put('/api/settings/prefs', patch)
    load()
  }

  return (
    <div className="page" style={{ maxWidth: 860 }}>
      <h1 className="page-title">设置</h1>
      <div className="page-subtitle">AI 批改服务商与学习偏好 · 数据仅保存在本机</div>

      <Card
        title="AI 批改服务商" size="small"
        extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => openModal()}>添加</Button>}
        style={{ marginBottom: 16 }}
      >
        {providers.length === 0 && (
          <Alert
            type="warning" showIcon
            message="尚未配置 AI 服务商"
            description="添加任一家 OpenAI 兼容服务的 API Key 即可启用真实批改。未配置时可开启「模拟批改」体验流程。"
            style={{ marginBottom: 12 }}
          />
        )}
        {!providers.some(p => p.service_type === 'codex') && <Button style={{ marginBottom: 12 }} onClick={async () => {
          try { await post('/api/settings/providers/codex'); await load(); message.success('已添加本机 Codex') } catch (e: any) { message.error(e.message) }
        }}>添加本机 Codex</Button>}
        {providers.map((p) => (
          <div
            key={p.id}
            style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '12px 4px',
              borderBottom: '1px solid #f4f5f7', flexWrap: 'wrap',
            }}
          >
            <div style={{ minWidth: 130 }}>
              <b>{p.name}</b> {p.is_default && <Tag color="blue">默认</Tag>}
            </div>
            <div style={{ flex: 1, minWidth: 200, color: '#777', fontSize: 13 }}>
              {p.service_type === 'codex' ? <><ApiOutlined /> 本机默认模型 · ChatGPT 登录
                <div style={{ marginTop: 4 }}>{codexStatus?.message || '正在检查登录状态…'}</div>
                <div style={{ marginTop: 4 }}>连接测试：{codexConnection ? codexConnection.message : '尚未测试'}</div></> : <><ApiOutlined /> {p.base_url} · 模型 <Tag>{p.model || '未设置'}</Tag> · Key {p.api_key_masked || '未设置'}
                <div style={{ marginTop: 4 }}>{MODE_LABELS[p.reasoning_mode]}{p.reasoning_effort && ` · 强度 ${EFFORT_LABELS[p.reasoning_effort] || p.reasoning_effort}`}</div></>}
            </div>
            <Space size={4}>
              <Button size="small" loading={testing === p.id} onClick={() => testProvider(p)}>测试</Button>
              {!p.is_default && (
                <Button size="small" icon={<CheckOutlined />} onClick={async () => { await post(`/api/settings/providers/${p.id}/default`); load() }} title="设为默认" />
              )}
              {p.service_type !== 'codex' && <Button size="small" icon={<EditOutlined />} onClick={() => openModal(p)} />}
              <Popconfirm title="确定删除该服务商？" onConfirm={() => removeProvider(p.id)}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Space>
          </div>
        ))}
      </Card>

      <Card title="学习偏好" size="small" style={{ marginBottom: 16 }}>
        {prefs && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <span style={{ width: 170 }}>每日新学单词上限</span>
              <InputNumber min={5} max={200} value={Number(prefs.daily_new_words)}
                onChange={(v) => v && savePrefs({ daily_new_words: v })} />
              <span style={{ color: '#999', fontSize: 12.5 }}>每天最多安排多少个新词进入学习队列</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <span style={{ width: 170 }}>每日新学短语上限</span>
              <InputNumber min={5} max={200} value={Number(prefs.daily_new_phrases)}
                onChange={(v) => v && savePrefs({ daily_new_phrases: v })} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ width: 170 }}>模拟批改（调试用）</span>
              <Switch checked={prefs.mock_mode === '1'} onChange={(v) => savePrefs({ mock_mode: v })} />
              <span style={{ color: '#999', fontSize: 12.5 }}>开启后提交练习不调用 AI，立即返回示例批改</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ width: 170 }}>自动发音</span>
              <Switch checked={prefs.auto_speak !== '0'} onChange={(v) => savePrefs({ auto_speak: v })} />
              <span style={{ color: '#999', fontSize: 12.5 }}>背单词/背短语换到下一张卡时自动朗读美式发音</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <span style={{ width: 170 }}>发音音量</span>
              <VolumeControl />
              <span style={{ color: '#999', fontSize: 12.5 }}>适用于所有词汇发音，自动记住本浏览器的设置</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <span style={{ width: 170 }}>自然发音</span>
              <span style={{ color: '#777', fontSize: 13 }}>统一美式女声 · 缩写按全称朗读</span>
              <Button onClick={() => speak('have / get a shot at (doing) sth', 'us')}>试听</Button>
            </div>
          </Space>
        )}
      </Card>

      <Card title="关于" size="small">
        <div style={{ color: '#777', fontSize: 13, lineHeight: 2 }}>
          英语学习平台 · 本地个人使用版<br />
          真题库：2019.12–2025.12 六级 38 套 + 2020–2026 考研英语二 7 年（翻译与写作题）<br />
          词库：ECDICT 开源词典（MIT License）筛选 · 六级 5407 词 / 考研 4801 词 / 考试短语 442 条<br />
          数据库与配置全部保存在本地 backend/data 目录，删除该目录即彻底清空数据。
        </div>
      </Card>

      <Modal
        title={editing ? '编辑服务商' : '添加服务商'} open={modalOpen}
        onCancel={() => setModalOpen(false)} onOk={saveProvider} okText="保存"
      >
        <Form form={form} layout="vertical" initialValues={{ is_default: false, service_type: 'custom', reasoning_mode: 'auto', reasoning_effort: '' }}>
          <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 8 }}>
            <span style={{ fontSize: 12.5, color: '#999' }}>快速填充：</span>
            <Space wrap>
              {presets.map((ps) => (
                <Button key={ps.name} size="small" onClick={() => form.setFieldsValue({ name: ps.name, service_type: ps.service_type,
                  base_url: ps.base_url, model: ps.model, reasoning_mode: 'auto', reasoning_effort: '' })}>{ps.name}</Button>
              ))}
            </Space>
          </Space>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 Anthropic / DeepSeek / 智谱 / OpenCode" />
          </Form.Item>
          <Form.Item name="service_type" label="接入方式">
            <Select options={[...presets.map(p => ({ value: p.service_type, label: p.name })), { value: 'custom', label: '自定义兼容 API' }]}
              onChange={value => { const p = presets.find(p => p.service_type === value); if (p) form.setFieldsValue({ base_url: p.base_url, model: p.model, reasoning_mode: 'auto', reasoning_effort: '' }) }} />
          </Form.Item>
          {formType === 'opencode_go' && <Alert type="info" showIcon style={{ marginBottom: 14 }} message="OpenCode Go 订阅独立接口"
            description={<span>使用 Go 订阅密钥，选择 Claude 后会自动匹配对应接口，无需改填官方密钥。平台自动发送客户端身份与稳定会话请求头。Go 官方面向编码代理；翻译批改适用范围、额度和超额设置以账户服务为准。<a href="https://opencode.ai/v2/docs/console/go/" target="_blank" rel="noreferrer">查看官方说明</a></span>} />}
          {formType === 'anthropic' && <Alert type="info" showIcon style={{ marginBottom: 14 }} message="Anthropic 官方服务"
            description={<span>填写 Anthropic 官方 API 密钥，此配置与 Go 订阅分别保存。选择 Claude 后，在下方设置该模型支持的推理模式和强度。<a href="https://platform.claude.com/docs/en/build-with-claude/thinking" target="_blank" rel="noreferrer">查看官方说明</a></span>} />}
          {formType === 'deepseek' && <div style={{ marginBottom: 12 }}><a href="https://api-docs.deepseek.com/guides/thinking_mode/" target="_blank" rel="noreferrer">DeepSeek 官方推理模式说明</a></div>}
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true, message: '请输入 Base URL' }]}>
            <Input placeholder="https://api.deepseek.com" />
          </Form.Item>
          <Form.Item name="model" label="模型名" rules={[{ required: true, message: '请输入模型名' }]}>
            <AutoComplete placeholder="选择模型或手动输入完整模型名" options={Array.from(new Map([
              ...(presets.find(p => p.service_type === formType)?.models || []),
              ...(editing && editing.base_url === formBase && editing.service_type === formType ? editing.models : []),
            ].map(m => [m.id, { value: m.id, label: m.name || m.id }])).values())}
              onChange={() => form.setFieldsValue({ reasoning_mode: 'auto', reasoning_effort: '' })} />
          </Form.Item>
          <Button size="small" disabled={!editing} loading={refreshing} style={{ marginBottom: 14 }} onClick={async () => {
            if (!editing) return
            setRefreshing(true)
            try { const p = await post<Provider>(`/api/settings/providers/${editing.id}/models`); setEditing(p); await load(); message.success('模型列表已刷新，原配置保留') }
            catch (e: any) { message.error(e.message) }
            finally { setRefreshing(false) }
          }}>刷新已保存服务的模型列表</Button>
          {!editing && <div style={{ color: '#999', fontSize: 12, marginBottom: 12 }}>保存配置后可在线刷新模型列表。</div>}
          <Form.Item name="reasoning_mode" label="推理模式" extra={caps.note}>
            <Select options={caps.modes.map(value => ({ value, label: MODE_LABELS[value] || value }))}
              onChange={value => { if (value === 'disabled') form.setFieldValue('reasoning_effort', '') }} />
          </Form.Item>
          <Form.Item name="reasoning_effort" label="推理强度">
            <Select disabled={formMode === 'disabled' || caps.levels.length === 0}
              options={[{ value: '', label: '模型默认' }, ...caps.levels.map(value => ({ value, label: EFFORT_LABELS[value] || value }))]} />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder="sk-…" autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
