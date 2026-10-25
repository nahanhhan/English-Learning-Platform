import {
  ApiOutlined, CheckOutlined, DeleteOutlined, EditOutlined, PlusOutlined,
} from '@ant-design/icons'
import {
  Alert, Button, Card, Empty, Form, Input, InputNumber, Modal, Popconfirm,
  Space, Switch, Tag, message,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { del, get, post, put } from '../api'
import VolumeControl from '../components/VolumeControl'
import { speak, stopSpeaking } from '../speak'

interface Provider {
  id: number
  name: string
  base_url: string
  api_key_masked: string
  model: string
  is_default: boolean
}

const PRESETS = [
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { name: '智谱 GLM', base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4.6' },
]

export default function Settings() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [prefs, setPrefs] = useState<any>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const [form] = Form.useForm()
  const [testing, setTesting] = useState<number | null>(null)

  const load = useCallback(async () => {
    const data = await get('/api/settings')
    setProviders(data.providers)
    setPrefs(data.prefs)
  }, [])

  useEffect(() => { load().catch((e) => message.error(e.message)) }, [load])
  useEffect(() => () => stopSpeaking(), [])

  const openModal = (p?: Provider) => {
    setEditing(p || null)
    form.resetFields()
    if (p) {
      form.setFieldsValue({ name: p.name, base_url: p.base_url, model: p.model, api_key: p.api_key_masked, is_default: p.is_default })
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
              <ApiOutlined /> {p.base_url} · 模型 <Tag>{p.model || '未设置'}</Tag> · Key {p.api_key_masked || '未设置'}
            </div>
            <Space size={4}>
              <Button size="small" loading={testing === p.id} onClick={() => testProvider(p)}>测试</Button>
              {!p.is_default && (
                <Button size="small" icon={<CheckOutlined />} onClick={async () => { await post(`/api/settings/providers/${p.id}/default`); load() }} title="设为默认" />
              )}
              <Button size="small" icon={<EditOutlined />} onClick={() => openModal(p)} />
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
        <Form form={form} layout="vertical" initialValues={{ is_default: false }}>
          <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 8 }}>
            <span style={{ fontSize: 12.5, color: '#999' }}>快速填充：</span>
            <Space>
              {PRESETS.map((ps) => (
                <Button key={ps.name} size="small" onClick={() => form.setFieldsValue(ps)}>{ps.name}</Button>
              ))}
            </Space>
          </Space>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 DeepSeek / 智谱 / OpenCode" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true, message: '请输入 Base URL' }]}>
            <Input placeholder="https://api.deepseek.com" />
          </Form.Item>
          <Form.Item name="model" label="模型名" rules={[{ required: true, message: '请输入模型名' }]}>
            <Input placeholder="deepseek-chat / glm-4.6 …" />
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
