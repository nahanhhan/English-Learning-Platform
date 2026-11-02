import { BookOutlined, ReloadOutlined, SendOutlined, StarOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Form, Input, Modal, Pagination, Select, Segmented, Space, Spin, Statistic, Table, Tag, message } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import ProviderSelect, { MODE_LABELS, EFFORT_LABELS } from '../components/ProviderSelect'
import { get } from '../api'
import { shortApi, shortPost, type ShortAttempt, type ShortQuestion, type ShortRun, type ShortStats } from '../shortTranslationApi'

type Tab = 'practice' | 'review' | 'bank' | 'history'
const CURRENT_KEY = 'elp:short:current'
const draftKey = (id: string) => `elp:short:draft:${id}`
function readLocal(key: string) { try { return localStorage.getItem(key) || '' } catch { return '' } }
function writeLocal(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* 草稿不可用不阻止作答 */ } }
const STATUS: Record<string, string> = { pending: '等待批改', grading: '批改中', done: '已批改', failed: '批改失败' }

function Feedback({ attempt, run, collect }: { attempt: ShortAttempt; run: ShortRun; collect: (note: { expr: string; translation: string; item_type: string }) => void }) {
  const result = attempt.result
  if (!result) return null
  return <div className="short-feedback">
    {attempt.mock && <Alert type="warning" showIcon message="模拟批改示例：不代表真实分数，不计入完成题量或复习巩固。" />}
    <Card size="small" title={attempt.is_revision ? '重译反馈' : '本次首答反馈'}>
      <div className="short-score-line"><Statistic title="训练评分" value={result.score} suffix="/ 15" />
        <Space wrap>{Object.entries(result.dimensions).map(([key, value]) => <Tag key={key}>
          {{ accuracy: '忠实准确', language: '语言质量', fluency: '表达流畅' }[key] || key} {value}/5
        </Tag>)}</Space></div>
      <p className="short-prose">{result.overall_comment}</p>
      {attempt.is_revision && <div className="short-comparison">
        <div><b>已解决的问题</b>{result.resolved_points.length ? <ul>{result.resolved_points.map((p, i) => <li key={i}>{p}</li>)}</ul> : <p>未报告新的已解决问题。</p>}</div>
        <div><b>仍需改进</b>{result.remaining_points.length ? <ul>{result.remaining_points.map((p, i) => <li key={i}>{p}</li>)}</ul> : <p>以逐句点评为准。</p>}</div>
      </div>}
    </Card>
    <Card title="逐句点评" size="small">
      {result.sentence_comments.map(item => <section key={item.sentence_index} className="short-sentence-feedback">
        <b>第 {item.sentence_index} 句</b><p className="short-source">{run.question.sentences[item.sentence_index - 1]}</p>
        <div className="short-quote">{item.translation || '未定位到单独译文片段，请结合整段作答与点评查看。'}</div>
        <p>{item.comment}</p>
        {item.errors.map((text, i) => <p key={i}><Tag color="red">错误</Tag>{text}</p>)}
        {item.improvements.map((text, i) => <p key={i}><Tag color="blue">可优化</Tag>{text}</p>)}
        {item.suggestion && <p><b>修改建议：</b>{item.suggestion}</p>}
      </section>)}
    </Card>
    <div className="short-versions">
      <Card size="small" title="在你的译文上修改"><p className="short-prose short-english">{result.improved_version}</p></Card>
      <Card size="small" title="题库参考译文"><p className="short-prose short-english">{run.reference}</p>
        <div style={{ color: '#8c96a7', fontSize: 12 }}>参考译文不是唯一正确答案，准确自然的不同译法同样认可。</div></Card>
    </div>
    {run.training_points.length > 0 && <Card title="本题训练重点" size="small"><Space wrap>{run.training_points.map(p => <Tag key={p}>{p}</Tag>)}</Space></Card>}
    {result.key_notes.length > 0 && <Card title="关键表达与用法" size="small">{result.key_notes.map((note, i) => <div className="short-expression" key={i}>
      <div><b>{note.expr}</b><p>{note.translation}</p><p style={{ color: '#778396' }}>{note.note}</p></div>
      <Button size="small" icon={<StarOutlined />} onClick={() => collect(note)}>加入平时积累</Button>
    </div>)}</Card>}
  </div>
}

export default function ShortTranslation() {
  const [tab, setTab] = useState<Tab>('practice')
  const [stats, setStats] = useState<ShortStats | null>(null)
  const [questions, setQuestions] = useState<ShortQuestion[]>([])
  const [topic, setTopic] = useState('')
  const [search, setSearch] = useState('')
  const [run, setRun] = useState<ShortRun | null>(null)
  const [answer, setAnswer] = useState('')
  const [providerId, setProviderId] = useState<number>()
  const [busy, setBusy] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const [pollError, setPollError] = useState('')
  const [selectedAttempt, setSelectedAttempt] = useState<number>()
  const [history, setHistory] = useState<{ total: number; items: ShortRun[] }>({ total: 0, items: [] })
  const [historyPage, setHistoryPage] = useState(1)
  const [collectOpen, setCollectOpen] = useState(false)
  const [collecting, setCollecting] = useState(false)
  const [groups, setGroups] = useState<{ id: number; name: string }[]>([])
  const [collectForm] = Form.useForm()
  const actionLock = useRef(false)
  const runEpoch = useRef(0)
  const pendingRequest = useRef<{ signature: string; id: string }>()
  const resultRef = useRef<HTMLDivElement>(null)
  const lastAttempt = run?.attempts[run.attempts.length - 1]
  const currentAttempt = run?.attempts.find(a => a.id === selectedAttempt) || lastAttempt
  const grading = lastAttempt?.status === 'pending' || lastAttempt?.status === 'grading'

  const loadData = useCallback(async () => {
    const [summary, items] = await Promise.all([shortApi<ShortStats>('/stats'), shortApi<ShortQuestion[]>('/questions')])
    setStats(summary); setQuestions(items)
  }, [])
  const openRun = useCallback(async (id: string) => {
    const epoch = ++runEpoch.current
    const data = await shortApi<ShortRun>(`/runs/${id}`)
    if (epoch !== runEpoch.current) return
    setRun(data); setSelectedAttempt(undefined); setPollError(''); setTab('practice')
    writeLocal(CURRENT_KEY, id)
  }, [])

  useEffect(() => {
    let alive = true
    loadData().catch(e => message.error(e.message))
    const id = readLocal(CURRENT_KEY)
    if (id) openRun(id).catch(e => { if (alive) message.info(`上次练习暂时无法读取：${e.message}`) })
      .finally(() => { if (alive) setRestoring(false) })
    else setRestoring(false)
    return () => { alive = false; runEpoch.current += 1 }
  }, [loadData, openRun])

  useEffect(() => {
    if (run) setAnswer(readLocal(draftKey(run.id)) || run.attempts[run.attempts.length - 1]?.content || '')
    pendingRequest.current = undefined
  }, [run?.id])

  useEffect(() => {
    if (!run || !grading) return
    const id = run.id
    let alive = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const data = await shortApi<ShortRun>(`/runs/${id}`)
        if (!alive) return
        setRun(data); setPollError('')
        const last = data.attempts[data.attempts.length - 1]
        if (last?.status === 'pending' || last?.status === 'grading') timer = setTimeout(poll, 1500)
        else { loadData().catch(() => {}); if (last?.status === 'done') resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
      } catch (e: any) {
        if (alive) { setPollError(`读取批改状态失败，作答已保留：${e.message}`); timer = setTimeout(poll, 4000) }
      }
    }
    timer = setTimeout(poll, 800)
    return () => { alive = false; clearTimeout(timer) }
  }, [run?.id, grading, loadData])

  useEffect(() => {
    if (tab !== 'history') return
    let alive = true
    shortApi<{ total: number; items: ShortRun[] }>(`/history?page=${historyPage}`)
      .then(data => { if (alive) setHistory(data) }).catch(e => message.error(e.message))
    return () => { alive = false }
  }, [tab, historyPage])

  function updateAnswer(value: string) {
    setAnswer(value)
    if (run) writeLocal(draftKey(run.id), value)
  }

  async function begin(questionId?: string, mode: 'new' | 'review' = 'new') {
    if (actionLock.current || grading) return
    const epoch = ++runEpoch.current
    actionLock.current = true; setBusy(true)
    try {
      const data = await shortPost<ShortRun>('/runs', { question_id: questionId, topic, mode })
      if (epoch !== runEpoch.current) return
      setRun(data); setTab('practice'); setSelectedAttempt(undefined); setPollError('')
      writeLocal(CURRENT_KEY, data.id)
    } catch (e: any) { message.info(e.message) }
    finally { actionLock.current = false; setBusy(false) }
  }

  async function submit() {
    if (!run || actionLock.current || grading) return
    if (!answer.trim()) { message.info('请先输入完整的英文译文'); return }
    actionLock.current = true; setBusy(true)
    const epoch = runEpoch.current
    const signature = `${run.id}:${providerId || 0}:${answer.trim()}`
    if (pendingRequest.current?.signature !== signature) pendingRequest.current = { signature, id: crypto.randomUUID() }
    try {
      await shortPost(`/runs/${run.id}/attempts`, { content: answer, provider_id: providerId, request_id: pendingRequest.current.id })
      if (epoch !== runEpoch.current) return
      pendingRequest.current = undefined
      const data = await shortApi<ShortRun>(`/runs/${run.id}`)
      if (epoch !== runEpoch.current) return
      setRun(data); setSelectedAttempt(undefined); setPollError('')
      loadData().catch(() => {})
    } catch (e: any) { message.error(`${e.message}。草稿已保留。`); if (epoch === runEpoch.current) {
      try { const data = await shortApi<ShortRun>(`/runs/${run.id}`); if (epoch === runEpoch.current) setRun(data) } catch { /* 保留同一请求编号便于安全重试 */ }
    } }
    finally { actionLock.current = false; setBusy(false) }
  }

  async function toggleReview(id: string, enabled: boolean) {
    try {
      await shortApi(`/questions/${id}/review`, { method: 'PUT', body: JSON.stringify({ enabled }) })
      await loadData()
      if (run?.question.id === id) setRun(current => current ? { ...current, in_review: enabled, streak: 0 } : current)
      message.success(enabled ? '已加入复习清单' : '已移出复习清单')
    } catch (e: any) { message.error(e.message) }
  }

  function openCollect(note: { expr: string; translation: string; item_type: string }) {
    collectForm.setFieldsValue({ english: note.expr, translation: note.translation,
      item_type: note.item_type === 'word' ? 'word' : 'phrase', group_id: 0 })
    get('/api/accumulation/groups').then(setGroups).catch(e => message.error(e.message))
    setCollectOpen(true)
  }

  async function collect() {
    if (!currentAttempt) return
    try {
      const fields = await collectForm.validateFields()
      setCollecting(true)
      const response = await shortPost<{ added: number; skipped: number }>(`/attempts/${currentAttempt.id}/collect`, { ...fields, group_id: fields.group_id || undefined })
      message.success(response.added ? '已加入平时单词短语积累' : '已有相同词条，保留原内容和学习进度')
      setCollectOpen(false)
    } catch (e: any) { if (e.message) message.error(e.message) }
    finally { setCollecting(false) }
  }

  const visibleQuestions = questions.filter(q => (!topic || q.topic === topic) &&
    (!search || (q.id + q.title + q.sentences.join('')).toLowerCase().includes(search.toLowerCase())) && (tab !== 'review' || q.in_review))

  return <div className="page short-page">
    <div className="short-toolbar"><div><h1 className="page-title">短句翻译</h1>
      <div className="page-subtitle">中译英强化练习 · 先独立表达，再逐句打磨</div></div>
      <Button type="primary" icon={<ReloadOutlined />} loading={busy} disabled={grading} onClick={() => begin()}>随机未做题</Button></div>
    <div className="short-stats">
      <Statistic title="已完成题目" value={stats?.completed || 0} suffix={`/ ${stats?.total || 0}`} />
      <Statistic title="待复习" value={stats?.review || 0} />
      <Statistic title="题目首答均分" value={stats?.first_average ?? '—'} suffix="/ 15" />
      <Statistic title="最近作答均分" value={stats?.latest_average ?? '—'} suffix="/ 15" />
    </div>
    <div className="short-navigation"><Segmented value={tab} onChange={value => setTab(value as Tab)} options={[
      { label: '练习', value: 'practice' }, { label: '复习清单', value: 'review' },
      { label: '题库', value: 'bank' }, { label: '历史与进步', value: 'history' },
    ]} /><Select aria-label="短句题目主题" value={topic} style={{ minWidth: 170 }} onChange={setTopic}
      options={[{ value: '', label: '全部主题' }, ...(stats?.topics || []).map(value => ({ value, label: value }))]} /></div>

    {tab === 'practice' && (restoring ? <div style={{ textAlign: 'center', padding: 50 }}><Spin /></div> : !run ?
      <Card className="short-start"><BookOutlined style={{ fontSize: 36, color: '#3562a7' }} /><h2>从一段短句开始</h2>
        <p>每题 1–3 句。整段提交后，查看逐句点评、修改版与参考译文。</p>
        <p>不计时，不限时；答前不展示提示，草稿自动保存。</p>
        <Button type="primary" size="large" onClick={() => begin()} loading={busy}>开始随机练习</Button></Card> : <div className="short-workspace">
        <Card className="short-question" title={<Space wrap><Tag color="blue">{run.question.topic}</Tag><b>{run.question.title}</b></Space>}
          extra={<Button size="small" onClick={() => toggleReview(run.question.id, !run.in_review)}>{run.in_review ? '移出复习清单' : '加入复习清单'}</Button>}>
          <div className="short-question-meta">{run.question.id} · {run.question.sentences.length} 句{run.is_review ? ` · 独立复习 ${run.streak}/3` : ''}</div>
          <p className="short-source">{run.question.sentences.join('')}</p><div className="short-source-note">{run.question.source}</div>
        </Card>
        <Card title="我的译文" size="small"><div style={{ marginBottom: 12 }}><ProviderSelect value={providerId} onChange={setProviderId} disabled={grading || busy} /></div>
          <Input.TextArea aria-label="短句英文译文" rows={6} maxLength={15000} value={answer} disabled={grading || busy}
            placeholder="在这里完成整段英文译文。Ctrl+Enter 提交批改。" onChange={e => updateAnswer(e.target.value)}
            onKeyDown={e => { if (e.ctrlKey && e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); void submit() } }} />
          <div className="short-answer-actions"><span>草稿自动保存；修改后再提交会保留原记录。</span>
            <Button type="primary" icon={<SendOutlined />} loading={busy || grading} onClick={submit}>{lastAttempt?.status === 'done' ? '提交修改版' : lastAttempt?.status === 'failed' ? '重新提交批改' : '提交批改'}</Button></div>
          {grading && <Alert type="info" showIcon style={{ marginTop: 12 }} message="AI 正在逐句批改，作答已保存，可稍后回来查看。" />}
          {pollError && <Alert type="warning" showIcon message={pollError} style={{ marginTop: 12 }} />}
          {lastAttempt?.status === 'failed' && <Alert type="error" showIcon style={{ marginTop: 12 }} message={lastAttempt.error} description="可在上方手动选择其他已配置服务，或保留原服务重新提交；不会自动切换。" />}
        </Card>
        {run.attempts.length > 0 && <div ref={resultRef}>
          <div className="short-version-toolbar"><Select aria-label="短句作答版本" style={{ width: 300, maxWidth: '100%' }}
            value={currentAttempt?.id} onChange={setSelectedAttempt} options={run.attempts.map((a, index) => ({ value: a.id,
              label: `${index + 1}. ${a.is_revision ? '修改' : '独立首答'} · ${STATUS[a.status]}${a.score != null ? ` ${a.score}/15` : ''}${a.mock ? '（模拟）' : ''}` }))} />
            <Button disabled={grading || busy} onClick={() => begin(run.question.id, run.in_review ? 'review' : 'new')}>重新独立练习</Button></div>
          {currentAttempt && <>
            <Card size="small" title="此版本作答与配置"><div className="short-prose short-english">{currentAttempt.content}</div>
              <div className="short-profile-note">{currentAttempt.mock ? '模拟批改' : currentAttempt.profile.name || '未配置服务'}
                {currentAttempt.profile.model && ` · ${currentAttempt.profile.model}`} · {MODE_LABELS[currentAttempt.profile.reasoning_mode] || '模型默认'}
                {currentAttempt.profile.reasoning_effort && ` · 强度 ${EFFORT_LABELS[currentAttempt.profile.reasoning_effort] || currentAttempt.profile.reasoning_effort}`}
              </div></Card>
            {currentAttempt.status === 'done' && <Feedback attempt={currentAttempt} run={run} collect={openCollect} />}
            {currentAttempt.status === 'failed' && currentAttempt !== lastAttempt && <Alert type="error" message={currentAttempt.error} />}
          </>}
        </div>}
      </div>)}

    {(tab === 'bank' || tab === 'review') && <Card>
      {tab === 'review' && <Alert type="info" showIcon style={{ marginBottom: 16 }} message="独立首答低于 12 分自动收录，也可手动管理。三个不同日期连续独立复习达标后移出；即时修改、模拟批改不计次，同日最多累计一次达标。" />}
      <Input.Search aria-label="搜索短句题目" placeholder="搜索题号、标题或原文" allowClear value={search} onChange={e => setSearch(e.target.value)} style={{ width: 320, maxWidth: '100%', marginBottom: 16 }} />
      <Table<ShortQuestion> rowKey="id" dataSource={visibleQuestions} scroll={{ x: 730 }} pagination={{ pageSize: 10 }} locale={{ emptyText: <Empty description={tab === 'review' ? '当前没有待复习题目' : '当前筛选没有题目'} /> }} columns={[
        { title: '题目', key: 'question', render: (_, q) => <><b>{q.id} · {q.title}</b><div style={{ marginTop: 6, color: '#778396' }}>{q.sentences.join('')}</div></> },
        { title: '主题', dataIndex: 'topic', width: 100 },
        { title: '首答', width: 85, render: (_, q) => q.first_score == null ? '未完成' : `${q.first_score}/15` },
        { title: '状态', width: 95, render: (_, q) => q.in_review ? <Tag color="orange">复习 {q.streak}/3</Tag> : <Tag color={q.completed ? 'green' : 'default'}>{q.completed ? q.streak >= 3 ? '已巩固' : '已练习' : '未做'}</Tag> },
        { title: '操作', width: 180, render: (_, q) => <Space wrap><Button size="small" disabled={grading || busy} onClick={() => begin(q.id, q.in_review ? 'review' : 'new')}>{q.in_review ? '独立复习' : '开始练习'}</Button>
          <Button size="small" type="text" onClick={() => toggleReview(q.id, !q.in_review)}>{q.in_review ? '移出' : '加入复习'}</Button></Space> },
      ]} />
    </Card>}

    {tab === 'history' && <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Card title="题目首答与最近成绩" size="small"><Table<ShortQuestion> size="small" rowKey="id" dataSource={stats?.performance || []} pagination={{ pageSize: 8 }} columns={[
        { title: '题目', dataIndex: 'title' }, { title: '首次独立首答', dataIndex: 'first_score', render: value => `${value}/15` },
        { title: '最近作答', dataIndex: 'latest_score', render: value => `${value}/15` },
      ]} /></Card>
      <Card title="练习历史" size="small">{history.items.length === 0 ? <Empty description="还没有练习记录" /> : history.items.map(record => <div key={record.id} className="short-history-row">
        <div><b>{record.question.title}</b><p>{record.is_review ? '独立复习' : '独立练习'} · {record.attempts.length} 个作答版本{!record.attempts.length ? ' · 尚未提交' : ''}</p></div>
        <Button disabled={grading || busy} onClick={() => openRun(record.id)}>打开记录 / 继续</Button>
      </div>)}<Pagination current={historyPage} pageSize={20} total={history.total} showSizeChanger={false} onChange={setHistoryPage} style={{ marginTop: 14, textAlign: 'right' }} /></Card>
    </Space>}

    <Modal title="核对后加入平时积累" open={collectOpen} onCancel={() => setCollectOpen(false)} onOk={collect} confirmLoading={collecting} okText="确认加入">
      <Form form={collectForm} layout="vertical">
        <Form.Item name="english" label="英文" rules={[{ required: true, whitespace: true, message: '请核对英文表达' }]}><Input maxLength={300} /></Form.Item>
        <Form.Item name="translation" label="中文释义" rules={[{ required: true, whitespace: true, message: '请输入简明中文释义' }]}><Input.TextArea rows={2} maxLength={5000} /></Form.Item>
        <Form.Item name="item_type" label="类型"><Select options={[{ value: 'word', label: '单词' }, { value: 'phrase', label: '短语 / 表达' }]} /></Form.Item>
        <Form.Item name="group_id" label="分组"><Select options={[{ value: 0, label: '短句翻译积累（默认分组）' }, ...groups.filter(g => g.name !== '短句翻译积累').map(g => ({ value: g.id, label: g.name }))]} /></Form.Item>
      </Form><p style={{ color: '#778396' }}>保留原题来源；积累库中同类型的重复词条跳过，不覆盖已有内容和学习进度。</p>
    </Modal>
  </div>
}
