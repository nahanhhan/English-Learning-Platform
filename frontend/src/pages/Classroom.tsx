import {
  BookOutlined, CheckCircleFilled, CloseCircleFilled, DeleteOutlined, EditOutlined,
  FileAddOutlined, FolderOutlined, PlusOutlined, SoundOutlined,
} from '@ant-design/icons'
import {
  Alert, Button, Card, Checkbox, Empty, Form, Input, type InputRef, Modal, Pagination, Popconfirm,
  Progress, Result, Segmented, Select, Space, Spin, Statistic, Table, Tag, message,
} from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { classroom, type ClassroomEntry, type ClassroomGroup, type ImportRow, type Kind,
  type PracticeRound, type PracticeSource } from '../classroomApi'
import { get } from '../api'
import { cancelPendingSpeech, speak, stopSpeaking } from '../speak'
import VolumeControl from '../components/VolumeControl'
import AmericanPhonetic from '../components/AmericanPhonetic'
import PartOfSpeech from '../components/PartOfSpeech'

type Tab = 'review' | 'mistakes' | 'browse'
const typeName = (kind: string) => kind === 'word' ? '单词' : '短语'
const DRAFT_PREFIX = 'classroom-spell:'
function readLocal(key: string) { try { return localStorage.getItem(key) || '' } catch { return '' } }
function writeLocal(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* 存储不可用不影响答题 */ } }
function clearLocal(key: string) { try { localStorage.removeItem(key) } catch { /* 忽略 */ } }

function AmericanAudio({ english }: { english: string }) {
  return <Button icon={<SoundOutlined />} onClick={() => speak(english, 'us')}>美式发音</Button>
}

export default function Classroom() {
  const [groups, setGroups] = useState<ClassroomGroup[]>([])
  const [group, setGroup] = useState<number | undefined>(() => Number(readLocal('classroom-group')) || undefined)
  const [kind, setKind] = useState<Kind>(() => {
    const value = readLocal('classroom-kind')
    return value === 'word' || value === 'phrase' ? value : 'all'
  })
  const [tab, setTab] = useState<Tab>('review')
  const [source, setSource] = useState<PracticeSource>(() => readLocal('classroom-source') === 'mistake' ? 'mistake' : 'normal')
  const [round, setRound] = useState<PracticeRound | null>(null)
  const [roundLoading, setRoundLoading] = useState(true)
  const [roundError, setRoundError] = useState('')
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [spell, setSpell] = useState('')
  const spellInputRef = useRef<InputRef>(null)
  const [autoSpeak, setAutoSpeak] = useState(false)
  const spokenRef = useRef('')
  const feedbackTimer = useRef<ReturnType<typeof setTimeout>>()
  const scope = `${group || 'all'}:${kind}:${source}`
  const scopeRef = useRef(scope)
  scopeRef.current = scope
  const actionLock = useRef(false)
  const actionEpoch = useRef(0)
  // 失败后保留请求编号，重试不会重复计分。
  const pendingAction = useRef<{ signature: string; body: object }>()
  const [refresh, setRefresh] = useState(0)

  const [entries, setEntries] = useState<ClassroomEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [listLoading, setListLoading] = useState(false)
  const [entryOpen, setEntryOpen] = useState(false)
  const [editing, setEditing] = useState<ClassroomEntry | null>(null)
  const [entryForm] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [groupOpen, setGroupOpen] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [editingGroup, setEditingGroup] = useState<number | null>(null)
  const [groupBusy, setGroupBusy] = useState(false)

  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [importRows, setImportRows] = useState<ImportRow[]>([])
  const [rawText, setRawText] = useState('')
  const [targetGroup, setTargetGroup] = useState<number>()
  const [importBusy, setImportBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const importEpoch = useRef(0)

  const params = new URLSearchParams({ item_type: kind, source })
  if (group) params.set('group_id', String(group))
  const query = params.toString()
  const groupOptions = groups.map(g => ({ value: g.id, label: g.name }))
  const current = round?.current
  const draftKey = current ? `${DRAFT_PREFIX}${round!.id}:${current.question_id}` : ''

  const loadGroups = useCallback(async () => {
    const data = await classroom<ClassroomGroup[]>('/groups')
    setGroups(data)
    setGroup(value => value && !data.some(g => g.id === value) ? undefined : value)
  }, [])
  useEffect(() => { loadGroups().catch(e => message.error(e.message)) }, [loadGroups, refresh])
  useEffect(() => { writeLocal('classroom-group', String(group || '')) }, [group])
  useEffect(() => { writeLocal('classroom-kind', kind) }, [kind])
  useEffect(() => { writeLocal('classroom-source', source) }, [source])
  useEffect(() => {
    let alive = true
    get('/api/settings').then(data => { if (alive) setAutoSpeak(data?.prefs?.auto_speak === '1') }).catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true
    setRunning(false); setRound(null); setRoundLoading(true); setRoundError('')
    setFeedback(null); setBusy(false); setSpell(''); stopSpeaking()
    actionEpoch.current += 1; actionLock.current = false; pendingAction.current = undefined
    clearTimeout(feedbackTimer.current)
    classroom<PracticeRound | null>(`/sessions/current?${query}`)
      .then(data => { if (alive) setRound(data) })
      .catch(e => { if (alive) setRoundError(e.message) })
      .finally(() => { if (alive) setRoundLoading(false) })
    return () => { alive = false; clearTimeout(feedbackTimer.current); stopSpeaking() }
  }, [query])

  useEffect(() => { setSpell(draftKey ? readLocal(draftKey) : '') }, [draftKey])
  // 异步判定时输入框会禁用，必须等重新启用后再聚焦；每次提交均处理连续输错。
  useEffect(() => {
    if (tab === 'review' && running && current?.stage === 'spell' && !busy && !entryOpen && !groupOpen && !importOpen) {
      spellInputRef.current?.focus({ preventScroll: true })
    }
  }, [tab, running, current?.stage, current?.question_id, round?.version, busy, entryOpen, groupOpen, importOpen])
  useEffect(() => {
    stopSpeaking()
  }, [tab, running, entryOpen, groupOpen, importOpen, current?.question_id])
  useEffect(() => { cancelPendingSpeech() }, [current?.stage])
  useEffect(() => () => { stopSpeaking(); clearTimeout(feedbackTimer.current) }, [])
  useEffect(() => {
    if (tab !== 'review' || !running || !autoSpeak || current?.stage !== 'choice') return
    const key = `${round!.id}:${current.question_id}`
    if (spokenRef.current === key) return
    spokenRef.current = key
    speak(current.english, 'us')
  }, [tab, running, autoSpeak, current, round?.id])

  useEffect(() => {
    if (tab === 'review') return
    let alive = true
    setListLoading(true)
    const listParams = new URLSearchParams({ item_type: kind, page: String(page), search,
      mistakes: String(tab === 'mistakes') })
    if (group) listParams.set('group_id', String(group))
    classroom<{ items: ClassroomEntry[]; total: number }>(`/entries?${listParams}`)
      .then(data => { if (alive) { setEntries(data.items); setTotal(data.total) } })
      .catch(e => { if (alive) message.error(e.message) })
      .finally(() => { if (alive) setListLoading(false) })
    return () => { alive = false }
  }, [tab, group, kind, page, search, refresh])

  async function begin(restart = false) {
    if (actionLock.current) return
    const requestedScope = scope
    const epoch = actionEpoch.current
    actionLock.current = true; setBusy(true)
    try {
      const data = await classroom<PracticeRound>('/sessions', { method: 'POST', body: JSON.stringify({
        group_id: group, item_type: kind, source, restart,
      }) })
      if (scopeRef.current === requestedScope && epoch === actionEpoch.current) {
        setRound(data); setRunning(true); setFeedback(null); setRoundError('')
      }
    } catch (e: any) { message.error(e.message) }
    finally { if (epoch === actionEpoch.current) { actionLock.current = false; setBusy(false) } }
  }

  async function submit(action: 'choice' | 'spell' | 'next', value = '') {
    if (!round || !current || actionLock.current) return
    if (action === 'spell' && !value.trim()) {
      message.info('请输入英文拼写')
      spellInputRef.current?.focus({ preventScroll: true })
      return
    }
    actionLock.current = true; setBusy(true)
    if (action === 'choice') setFeedback(value)
    const requestedScope = scope
    const epoch = actionEpoch.current
    const signature = `${round.id}:${current.question_id}:${action}:${value}`
    if (pendingAction.current?.signature !== signature) {
      pendingAction.current = { signature, body: { question_id: current.question_id,
        version: round.version, request_id: crypto.randomUUID(), action, value } }
    }
    try {
      const data = await classroom<PracticeRound>(`/sessions/${round.id}/actions`, {
        method: 'POST', body: JSON.stringify(pendingAction.current.body),
      })
      if (requestedScope !== scopeRef.current || epoch !== actionEpoch.current) return
      pendingAction.current = undefined
      if (action === 'choice') {
        await new Promise<void>(resolve => { feedbackTimer.current = setTimeout(resolve, 950) })
        if (requestedScope !== scopeRef.current || epoch !== actionEpoch.current) return
        setFeedback(null)
      }
      if (action === 'spell') {
        clearLocal(draftKey); setSpell('')
      }
      setRound(data); setRefresh(n => n + 1)
    } catch (e: any) {
      if (epoch === actionEpoch.current) setFeedback(null)
      message.error(`${e.message}。可重试，已保存的结果不会重复计分。`)
      // 服务端成功但响应中断时，重新读取真实阶段。
      try {
        const data = await classroom<PracticeRound | null>(`/sessions/current?${query}`)
        if (requestedScope === scopeRef.current && epoch === actionEpoch.current) {
          setRound(data)
          if (!data) setRunning(false)
        }
      } catch { /* 保留界面和请求编号以便重试 */ }
    } finally {
      if (epoch === actionEpoch.current) { actionLock.current = false; setBusy(false) }
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (tab !== 'review' || !running || busy || entryOpen || groupOpen || importOpen || event.ctrlKey || event.metaKey || event.altKey) return
      const target = event.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'BUTTON', 'SELECT'].includes(target.tagName) || target.isContentEditable || document.querySelector('.ant-modal-open')) return
      if (current?.stage === 'choice' && /^[1-4]$/.test(event.key)) {
        const option = current.options[Number(event.key) - 1]
        if (option) { event.preventDefault(); void submit('choice', option) }
      }
      if (current?.stage === 'done' && event.key === 'Enter') { event.preventDefault(); void submit('next') }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  function openEntry(entry: ClassroomEntry | null = null) {
    setEditing(entry)
    entryForm.setFieldsValue(entry || { english: '', translation: '', item_type: 'word', group_id: group || groups[0]?.id })
    setEntryOpen(true)
  }
  async function saveEntry() {
    try {
      const data = await entryForm.validateFields()
      setSaving(true)
      await classroom(editing ? `/entries/${editing.id}` : '/entries', {
        method: editing ? 'PUT' : 'POST', body: JSON.stringify({ ...data, source: editing?.source || '' }),
      })
      setEntryOpen(false); setRefresh(n => n + 1); message.success('词条已保存，新一轮练习生效')
    } catch (e: any) { if (e.message) message.error(e.message) }
    finally { setSaving(false) }
  }
  async function saveGroup() {
    if (!groupName.trim() || groupBusy) return
    setGroupBusy(true)
    try {
      const result = await classroom<ClassroomGroup>(editingGroup ? `/groups/${editingGroup}` : '/groups', {
        method: editingGroup ? 'PUT' : 'POST', body: JSON.stringify({ name: groupName }),
      })
      await loadGroups(); setGroup(result.id); setGroupOpen(false); setGroupName(''); setEditingGroup(null)
      message.success('分组已保存')
    } catch (e: any) { message.error(e.message) }
    finally { setGroupBusy(false) }
  }

  function openImport() {
    importEpoch.current += 1
    setImportOpen(true); setImportRows([]); setImportText(''); setRawText('')
    setTargetGroup(group || groups[0]?.id)
  }
  async function preview(file?: File) {
    const epoch = ++importEpoch.current
    setImportBusy(true)
    try {
      const data = await classroom<{ rows: Omit<ImportRow, 'key' | 'included'>[]; raw_text: string }>(
        file ? `/imports/file?filename=${encodeURIComponent(file.name)}` : '/imports/text', {
          method: 'POST', headers: { 'Content-Type': file ? 'application/octet-stream' : 'application/json' },
          body: file || JSON.stringify({ text: importText }),
        })
      if (epoch !== importEpoch.current) return
      setImportRows(data.rows.map((row, index) => ({ ...row, key: index,
        included: !!row.english.trim() && !!row.translation.trim(), group_id: targetGroup })))
      setRawText(data.raw_text)
      if (!data.rows.length) message.info('没有找到词条，请检查粘贴内容')
    } catch (e: any) { if (epoch === importEpoch.current) message.error(e.message) }
    finally { setImportBusy(false) }
  }
  function editImportRow(key: number, patch: Partial<ImportRow>) {
    setImportRows(rows => rows.map(row => row.key === key ? { ...row, ...patch } : row))
  }
  async function confirmImport() {
    const rows = importRows.filter(row => row.included)
    if (!rows.length) { message.info('请至少勾选一条词汇'); return }
    if (rows.some(row => !row.english.trim() || !row.translation.trim() || !(row.group_id || targetGroup))) {
      message.error('请补齐所选条目的英文、中文释义和分组'); return
    }
    setImportBusy(true)
    try {
      const result = await classroom<{ added: number; skipped: number }>('/imports/confirm', {
        method: 'POST', body: JSON.stringify({ rows: rows.map(row => ({ ...row, group_id: row.group_id || targetGroup })) }),
      })
      setImportOpen(false); setRefresh(n => n + 1)
      message.success(`已导入 ${result.added} 条，跳过 ${result.skipped} 条重复词汇`)
    } catch (e: any) { message.error(e.message) }
    finally { setImportBusy(false) }
  }

  const selectedGroups = groups.filter(g => !group || g.id === group)
  const wordCount = selectedGroups.reduce((n, g) => n + (kind === 'all' ? g.total : kind === 'word' ? g.words : g.phrases), 0)
  const mistakeCount = selectedGroups.reduce((n, g) => n + (kind === 'all' ? g.mistakes : kind === 'word' ? g.word_mistakes : g.phrase_mistakes), 0)
  const spellHint = (current?.english || '').split('').map((ch, index) =>
    index === 0 || !/[a-zA-Z]/.test(ch) ? ch : '_').join(' ')

  function renderReview() {
    if (roundLoading) return <div className="classroom-empty"><Spin tip="读取已保存进度…" /></div>
    if (roundError) return <Alert type="error" message="进度读取失败" description={roundError} action={
      <Button onClick={() => { void classroom<PracticeRound | null>(`/sessions/current?${query}`).then(data => {
        setRound(data); setRoundError('')
      }).catch(e => message.error(e.message)) }}>重试</Button>} />
    if (!running) return <Card className="classroom-start">
      <BookOutlined style={{ fontSize: 44, color: '#3562a7' }} />
      <h2>{source === 'mistake' ? '错题专项练习' : '从课堂学过的词开始'}</h2>
      <p>{source === 'mistake' ? '只练当前范围的错题，连续 3 次全部答对后移出错题本。' : '每个单词和短语先选意思，再练拼写。进度自动保存，随时回来继续。'}</p>
      {round && !round.finished && <Alert style={{ textAlign: 'left', marginBottom: 20 }} type="info" showIcon
        message={`上次已完成 ${round.completed} / ${round.total} 题，${round.current?.stage === 'spell' ? '正在拼写' : round.current?.stage === 'done' ? '已保存当前题结果' : '正在选择释义'}`}
        description={`保存于 ${round.updated_at.replace('T', ' ').slice(0, 16)}`} />}
      <Space wrap>
        <Button type="primary" size="large" loading={busy} disabled={!wordCount} onClick={() => begin(!!round?.finished)}>
          {round && !round.finished ? '继续上次复习' : round?.finished ? '开始新一轮' : '开始复习'}
        </Button>
        {round && !round.finished && <Popconfirm title="重新开始会替换当前范围的未完成轮次，错题记录保留。" onConfirm={() => begin(true)}>
          <Button size="large" disabled={busy}>重新开始</Button>
        </Popconfirm>}
        {!wordCount && <Button onClick={openImport}>添加首批词汇</Button>}
      </Space>
    </Card>
    if (!round) return <Empty description="当前没有可继续的轮次" />
    if (round.finished) return <Card><Result status="success" title="本轮复习完成" subTitle={`完成 ${round.completed} 题 · 首次全部答对 ${round.correct} 题 · 错题已保存`} extra={[
      <Button key="again" type="primary" loading={busy} onClick={() => begin(true)}>再练一轮</Button>,
      <Button key="mistakes" onClick={() => { setTab('mistakes'); setPage(1) }}>查看错题本</Button>,
    ]} /></Card>
    if (!current) return <Empty description="当前题目不存在" />
    return <>
      <div className="classroom-question-meta"><Space wrap><Tag color="blue">{typeName(current.item_type)}</Tag>
        <span>{current.group_name}</span>{current.in_mistake_book && <Tag color="volcano">错题连对 {current.mistake_consec}/3</Tag>}
      </Space><span>已完成 {round.completed} / {round.total}</span></div>
      <Progress percent={Math.round(round.completed / Math.max(round.total, 1) * 100)} showInfo={false} />
      <Card className="classroom-practice-card">
        {current.stage === 'choice' && <>
          <div className="classroom-prompt"><h2>{current.english}
            {current.item_type === 'word' && <PartOfSpeech value={current.part_of_speech} />}</h2>
            {current.item_type === 'word' && <AmericanPhonetic value={current.phonetic_us} />}
            <AmericanAudio english={current.english} />
            <p>选择正确的中文意思 · 可按数字键 1–4</p></div>
          <div className="practice-options">
            {current.options.map((option, index) => {
              const correct = option === current.translation
              const selected = feedback === option
              return <Button key={option} block disabled={busy} size="large" className="classroom-option"
                style={feedback ? { background: correct ? '#f6ffed' : selected ? '#fff1f0' : undefined,
                  borderColor: correct ? '#b7eb8f' : selected ? '#ffa39e' : undefined } : {}}
                onClick={() => submit('choice', option)}>
                <span className="classroom-option-number">{index + 1}</span>{option}
                {feedback && correct && <CheckCircleFilled style={{ color: '#52c41a', marginLeft: 8 }} />}
                {feedback && selected && !correct && <CloseCircleFilled style={{ color: '#f5222d', marginLeft: 8 }} />}
              </Button>
            })}
          </div>
        </>}
        {current.stage === 'spell' && <>
          <div className="classroom-prompt"><div className="classroom-meaning">{current.translation}</div>
            <AmericanAudio english={current.english} />
            <p>{current.picked === current.translation ? `拼写这个${typeName(current.item_type)}` : '选择有误，继续拼写加深记忆'}</p>
            <div className="classroom-spell-hint">{current.spell_wrong ? current.english : spellHint}
              {current.item_type === 'word' && <PartOfSpeech value={current.part_of_speech} />}</div>
          </div>
          {current.spell_wrong && <Alert type="warning" showIcon message="首次拼写有误，已计入错题本。请照正确拼写重输一次。" style={{ marginBottom: 18 }} />}
          <Space.Compact style={{ width: '100%' }}>
            <Input ref={spellInputRef} key={current.question_id} autoFocus size="large" aria-label="英文拼写" placeholder="输入完整英文后回车"
              autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false}
              value={spell} disabled={busy} onChange={e => { setSpell(e.target.value); writeLocal(draftKey, e.target.value) }}
              onPressEnter={e => { if (!e.nativeEvent.isComposing) void submit('spell', spell) }} />
            <Button size="large" type="primary" loading={busy} onClick={() => submit('spell', spell)}>提交拼写</Button>
          </Space.Compact>
          <p className="classroom-note">按教材词条填写，sb / sth 等占位写法保留；大小写和多余空格不影响判断。</p>
        </>}
        {current.stage === 'done' && <div className="classroom-prompt">
          {current.rating === 'good' ? <CheckCircleFilled style={{ color: '#52c41a', fontSize: 44 }} /> : <CloseCircleFilled style={{ color: '#e6a23c', fontSize: 44 }} />}
          <h2>{current.rating === 'good' ? '选择和拼写全部正确' : current.rating === 'hard' ? '拼写已纠正，继续巩固' : '继续练习，加深记忆'}</h2>
          <div className="classroom-meaning">{current.english}
            {current.item_type === 'word' && <PartOfSpeech value={current.part_of_speech} />}</div><p>{current.translation}</p>
          <p>{current.in_mistake_book ? `已保存在错题本 · 连对 ${current.mistake_consec}/3` : '本题进度已保存'}</p>
          <Button size="large" type="primary" loading={busy} onClick={() => submit('next')}>
            {round.completed >= round.total ? '查看本轮结果' : '下一题'}
          </Button>
        </div>}
      </Card>
      <p className="classroom-note" style={{ textAlign: 'center' }}>进度自动保存 · <Button type="link" size="small" onClick={() => setRunning(false)}>暂停复习</Button></p>
    </>
  }

  return <div className="page classroom-page">
    <div className="classroom-toolbar">
      <div><h1 className="page-title">课内生词和短语</h1><div className="page-subtitle">把课上学过的词记牢 · 选意思，再拼写 · 随时继续上次进度</div></div>
      <Space wrap><VolumeControl /><Button icon={<FolderOutlined />} onClick={() => { setEditingGroup(null); setGroupName(''); setGroupOpen(true) }}>管理分组</Button>
        <Button icon={<FileAddOutlined />} onClick={openImport}>批量添加 / 导入</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEntry()}>添加词汇</Button></Space>
    </div>
    <div className="classroom-filters"><Select aria-label="课内分组" value={group || 0} style={{ minWidth: 230, maxWidth: '100%' }}
      options={[{ value: 0, label: '全部分组' }, ...groupOptions]} onChange={value => { setGroup(value || undefined); setPage(1) }} />
      <Segmented value={kind} options={[{ label: '全部词汇', value: 'all' }, { label: '单词', value: 'word' }, { label: '短语', value: 'phrase' }]}
        onChange={value => { setKind(value as Kind); setPage(1) }} />
    </div>
    <div className="classroom-stats">
      <Card size="small"><Statistic title="当前范围词汇" value={wordCount} suffix="条" /></Card>
      <Card size="small"><Statistic title="错题本" value={mistakeCount} suffix="条" valueStyle={{ color: '#c96b3a' }} /></Card>
      <Card size="small"><Statistic title="当前轮次完成" value={round?.completed || 0} suffix={`/ ${round?.total || 0}`} /></Card>
    </div>
    <div className="classroom-navigation">
      <Segmented value={tab} options={[{ label: '复习', value: 'review' }, { label: '错题本', value: 'mistakes' }, { label: '词表', value: 'browse' }]}
        onChange={value => { setTab(value as Tab); setPage(1); setSearch('') }} />
      {tab === 'review' && <Segmented value={source} options={[{ label: '全部复习', value: 'normal' }, { label: '错题专项', value: 'mistake' }]}
        onChange={value => setSource(value as PracticeSource)} />}
    </div>
    {tab === 'review' ? <div className="classroom-review">
      {renderReview()}
    </div> : <Card style={{ marginTop: 18 }}>
      <div className="classroom-toolbar" style={{ marginBottom: 16 }}>
        <Input.Search allowClear placeholder="搜索英文或中文释义" aria-label="搜索课内词汇" style={{ width: 280, maxWidth: '100%' }}
          value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} />
        {tab === 'mistakes' && <Button type="primary" disabled={!total} onClick={() => { setSource('mistake'); setTab('review'); setRunning(false) }}>错题专项练习</Button>}
      </div>
      {tab === 'mistakes' && <Alert type="info" showIcon message="选错意思或首次拼写出错会入本；连续 3 次选择、拼写全部正确后移出。" style={{ marginBottom: 16 }} />}
      <Table<ClassroomEntry> rowKey="id" loading={listLoading} dataSource={entries} pagination={false} scroll={{ x: 780 }}
        locale={{ emptyText: <Empty description={tab === 'mistakes' ? '当前范围没有错题，继续保持！' : '还没有词汇，添加或导入你的课堂笔记吧'} /> }}
        columns={[
          { title: '英文', dataIndex: 'english', width: 200, render: (value, entry) => <><b>{value}</b>
            {entry.item_type === 'word' && <PartOfSpeech value={entry.part_of_speech} />}
            {entry.item_type === 'word' && <AmericanPhonetic value={entry.phonetic_us} />}
            <div><Tag>{typeName(entry.item_type)}</Tag></div></> },
          { title: '中文释义', dataIndex: 'translation', render: value => <span style={{ whiteSpace: 'pre-wrap' }}>{value}</span> },
          { title: '分组', dataIndex: 'group_name', width: 160 },
          { title: '状态', width: 110, render: (_, entry) => entry.in_mistake_book ? <Tag color="volcano">连对 {entry.mistake_consec}/3</Tag> : <Tag color={entry.completed ? 'green' : 'default'}>{entry.completed ? '已练习' : '未练习'}</Tag> },
          { title: '操作', width: 180, render: (_, entry) => <Space wrap size={4}>
            <Button size="small" icon={<SoundOutlined />} aria-label={`播放 ${entry.english} 美式发音`} onClick={() => speak(entry.english, 'us')} />
            <Button size="small" icon={<EditOutlined />} aria-label={`编辑 ${entry.english}`} onClick={() => openEntry(entry)} />
            <Popconfirm title="删除该词汇？未完成的练习将跳过它。" onConfirm={async () => {
              try { await classroom(`/entries/${entry.id}`, { method: 'DELETE' }); setRefresh(n => n + 1) } catch (e: any) { message.error(e.message) }
            }}><Button size="small" danger icon={<DeleteOutlined />} aria-label={`删除 ${entry.english}`} /></Popconfirm>
          </Space> },
        ]} />
      <Pagination style={{ marginTop: 18, textAlign: 'right' }} current={page} pageSize={30} total={total} showSizeChanger={false} onChange={setPage} />
    </Card>}

    <Modal title={editing ? '编辑课内词汇' : '添加课内词汇'} open={entryOpen} onCancel={() => setEntryOpen(false)} onOk={saveEntry} confirmLoading={saving} okText="保存">
      <Form form={entryForm} layout="vertical">
        <Form.Item name="group_id" label="所属分组" rules={[{ required: true, message: '请选择分组' }]}><Select options={groupOptions} placeholder="先建立课程或单元分组" /></Form.Item>
        <Form.Item name="item_type" label="类型"><Select options={[{ value: 'word', label: '单词' }, { value: 'phrase', label: '短语' }]} /></Form.Item>
        <Form.Item name="english" label="英文" rules={[{ required: true, whitespace: true, message: '请输入英文' }]}><Input maxLength={300} /></Form.Item>
        <Form.Item name="translation" label="中文释义" rules={[{ required: true, whitespace: true, message: '请输入中文释义' }]}><Input.TextArea rows={3} maxLength={5000} placeholder="可注明词性，如 n. 名词释义；adj. 形容词释义" /></Form.Item>
      </Form>
      {!groups.length && <Button onClick={() => { setEditingGroup(null); setGroupName(''); setGroupOpen(true) }}>新建分组</Button>}
    </Modal>

    <Modal title="课程 / 单元分组" open={groupOpen} onCancel={() => setGroupOpen(false)} footer={null}>
      <Space.Compact style={{ width: '100%', margin: '12px 0 20px' }}><Input maxLength={200} placeholder="例如 大学英语 Unit 1" aria-label="分组名称"
        value={groupName} onChange={e => setGroupName(e.target.value)} onPressEnter={saveGroup} />
        <Button type="primary" loading={groupBusy} onClick={saveGroup}>{editingGroup ? '保存名称' : '新建分组'}</Button></Space.Compact>
      {groups.map(g => <div className="classroom-group-row" key={g.id}><span>{g.name}<small> · {g.total} 条</small></span><Space>
        <Button size="small" onClick={() => { setEditingGroup(g.id); setGroupName(g.name) }}>重命名</Button>
        <Popconfirm title={`删除“${g.name}”及其中 ${g.total} 条词汇和错题记录？`} onConfirm={async () => {
          try { await classroom(`/groups/${g.id}`, { method: 'DELETE' }); setRefresh(n => n + 1) } catch (e: any) { message.error(e.message) }
        }}><Button size="small" danger>删除</Button></Popconfirm>
      </Space></div>)}
    </Modal>

    <Modal title="批量添加 / 文件导入" open={importOpen} width={1080} maskClosable={false}
      onCancel={() => { importEpoch.current += 1; setImportOpen(false) }}
      footer={<Space><Button disabled={importBusy} onClick={() => { importEpoch.current += 1; setImportOpen(false) }}>取消</Button>
        <Button type="primary" loading={importBusy} disabled={!importRows.length} onClick={confirmImport}>导入已勾选词汇</Button></Space>}>
      <Alert type="info" showIcon message="支持 PDF（含扫描版）、Word .docx；只读取已有的英文和中文词表。请核对预览后导入。" style={{ margin: '16px 0' }} />
      <Space wrap style={{ marginBottom: 12 }}><span>默认目标分组</span><Select style={{ minWidth: 220 }} options={groupOptions} placeholder="请选择分组" value={targetGroup}
        onChange={value => { setTargetGroup(value); setImportRows(rows => rows.map(row => ({ ...row, group_id: value }))) }} />
        <Button onClick={() => { setEditingGroup(null); setGroupName(''); setGroupOpen(true) }}>新建分组</Button></Space>
      <Input.TextArea rows={4} aria-label="批量粘贴词汇" placeholder={'每行一条，英文和中文用制表符或竖线分隔，例如：\nreluctant | 不愿意的\nreason with | 跟……讲理'} value={importText} onChange={e => setImportText(e.target.value)} />
      <Space wrap style={{ margin: '12px 0 18px' }}><Button loading={importBusy} disabled={!importText.trim()} onClick={() => preview()}>生成粘贴预览</Button>
        <Button icon={<FileAddOutlined />} disabled={importBusy} onClick={() => fileRef.current?.click()}>选择 PDF / Word</Button>
        <input ref={fileRef} type="file" accept=".pdf,.docx,.doc" hidden onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void preview(file) }} />
        {importBusy && <span>正在处理，请稍候…</span>}</Space>
      {importRows.length > 0 && <>
        <p>共 {importRows.length} 条，已勾选 {importRows.filter(row => row.included).length} 条。同组同类型的重复英文会跳过，原学习记录保留。</p>
        <Table<ImportRow> size="small" rowKey="key" dataSource={importRows} scroll={{ x: 800 }} pagination={{ pageSize: 10 }} columns={[
          { title: '收录', width: 55, render: (_, row) => <Checkbox aria-label={`收录第 ${row.key + 1} 条`} checked={row.included} onChange={e => editImportRow(row.key, { included: e.target.checked })} /> },
          { title: '英文', width: 200, render: (_, row) => <Input aria-label={`第 ${row.key + 1} 条英文`} status={!row.english.trim() ? 'error' : undefined} placeholder="缺少英文" value={row.english} onChange={e => editImportRow(row.key, { english: e.target.value })} /> },
          { title: '中文释义', width: 240, render: (_, row) => <Input.TextArea aria-label={`第 ${row.key + 1} 条释义`} autoSize={{ maxRows: 3 }} status={!row.translation.trim() ? 'error' : undefined} placeholder="缺少释义，请核对原文" value={row.translation} onChange={e => editImportRow(row.key, { translation: e.target.value })} /> },
          { title: '类型', width: 100, render: (_, row) => <Select value={row.item_type} options={[{ value: 'word', label: '单词' }, { value: 'phrase', label: '短语' }]} onChange={value => editImportRow(row.key, { item_type: value })} /> },
          { title: '分组', width: 180, render: (_, row) => <Select style={{ width: '100%' }} options={groupOptions} value={row.group_id || targetGroup} onChange={value => editImportRow(row.key, { group_id: value })} /> },
          { title: '提取原文', width: 220, render: (_, row) => <small>{row.raw}</small> },
        ]} />
      </>}
      {rawText && <details style={{ marginTop: 14 }}><summary>查看完整提取原文（无法配对的内容可在上方重新粘贴整理）</summary><pre className="classroom-raw">{rawText}</pre></details>}
    </Modal>
  </div>
}
