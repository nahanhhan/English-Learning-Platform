import { ReloadOutlined, SendOutlined } from '@ant-design/icons'
import {
  Alert, Badge, Button, Empty, Input, Modal, Radio, Segmented, Select, Space,
  Spin, Statistic, Switch, Tag, message,
} from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { get, post, type Question, type Submission, type Grading } from '../api'
import GradingResult from '../components/GradingResult'

const Q_TYPE_LABEL: Record<string, string> = {
  translation: '翻译',
  writing: '写作',
  small_writing: '应用文',
  big_writing: '图表作文',
}

type Mode = 'translation' | 'writing'

export default function Practice({ mode }: { mode: Mode }) {
  const qTypes: string[] = mode === 'translation' ? ['translation'] : ['writing', 'small_writing', 'big_writing']

  const [examType, setExamType] = useState<string>('cet6')
  const [qType, setQType] = useState<string>(qTypes[0])
  const [year, setYear] = useState<number | null>(null)
  const [meta, setMeta] = useState<any>(null)
  const [questions, setQuestions] = useState<Question[]>([])
  const [current, setCurrent] = useState<Question | null>(null)
  const [answer, setAnswer] = useState('')
  const [freeMode, setFreeMode] = useState(false)
  const [freeSource, setFreeSource] = useState('')
  const [freeTitle, setFreeTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submission, setSubmission] = useState<Submission | null>(null)
  const [grading, setGrading] = useState<Grading | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [chartPreview, setChartPreview] = useState<'clear' | 'original' | null>(null)
  const [countdownOn, setCountdownOn] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [running, setRunning] = useState(false)
  const timerRef = useRef<any>(null)

  const isWriting = mode === 'writing'
  const wordCount = useMemo(() => answer.trim().split(/\s+/).filter(Boolean).length, [answer])
  const resultRef = useRef<HTMLDivElement>(null)
  const questionRequest = useRef(0)

  // 草稿自动保存：按题目区分，自由练习独立保存
  const draftKey = freeMode ? 'elp:draft:free' : `elp:draft:q${current?.id ?? 0}`

  const loadQuestions = useCallback(async () => {
    const request = ++questionRequest.current
    const params = new URLSearchParams({ exam_type: examType, q_type: qType })
    if (year) params.set('year', String(year))
    const data = await get<Question[]>(`/api/questions?${params}`)
    if (request !== questionRequest.current) return
    setQuestions(data)
    setCurrent((c) => (c && data.find((d) => d.id === c.id)) || data[0] || null)
    setSubmission(null)
    setGrading(null)
  }, [examType, qType, year])

  useEffect(() => {
    get('/api/questions/meta').then(setMeta).catch(() => {})
  }, [])

  useEffect(() => {
    loadQuestions().catch((e) => message.error(String(e.message || e)))
    return () => { questionRequest.current += 1 }
  }, [loadQuestions])

  // 切换 writing/translation 时重置题型
  useEffect(() => {
    setQType(qTypes[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  // 切题 / 切自由练习时恢复草稿
  useEffect(() => {
    try {
      setAnswer(localStorage.getItem(draftKey) || '')
    } catch {
      setAnswer('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey])

  // 作答变化实时存草稿
  const updateAnswer = (v: string) => {
    setAnswer(v)
    try {
      if (v) localStorage.setItem(draftKey, v)
      else localStorage.removeItem(draftKey)
    } catch { /* 本地存储不可用时静默 */ }
  }

  // 倒计时
  useEffect(() => {
    if (running) {
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000)
    }
    return () => clearInterval(timerRef.current)
  }, [running])

  const loadHistory = useCallback(async () => {
    const params = new URLSearchParams({ q_type: qType, page_size: '50' })
    const data = await get(`/api/practice/history?${params}`)
    setHistory(data.items || [])
  }, [qType])

  const pollResult = useCallback(async (sid: number, delay = 1500) => {
    const data = await get<{ submission: Submission; grading: Grading | null }>(`/api/practice/${sid}`)
    if (data.submission.status === 'done' || data.submission.status === 'failed') {
      setSubmission(data.submission)
      setGrading(data.grading)
      setSubmitting(false)
      setRunning(false)
      loadHistory().catch(() => {})
      if (data.submission.status === 'done') {
        try { localStorage.removeItem(draftKey) } catch { /* ignore */ }
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150)
      }
      return
    }
    setSubmission(data.submission)
    setTimeout(() => pollResult(sid, delay), delay)
  }, [loadHistory, draftKey])

  const onSubmit = async () => {
    const content = answer.trim()
    if (!content) return message.warning('请先输入你的作答')
    if (freeMode && !freeSource.trim()) return message.warning('自由练习请在左侧粘贴原文段落')
    setSubmitting(true)
    setGrading(null)
    setSubmission(null)
    try {
      const body = freeMode
        ? {
            exam_type: examType, q_type: qType,
            title: freeTitle.trim() || '自由练习',
            prompt: isWriting ? (freeTitle.trim() || '自由写作') : '翻译以下段落。',
            source_text: freeSource, content,
          }
        : { question_id: current!.id, content }
      const resp = await post<{ submission_id: number }>('/api/practice/submit', body)
      try { localStorage.removeItem(draftKey) } catch { /* ignore */ }
      message.success('已提交，AI 批改中…')
      pollResult(resp.submission_id)
    } catch (e: any) {
      setSubmitting(false)
      message.error(e.message || '提交失败')
    }
  }

  const regrade = async () => {
    if (!submission) return
    setSubmitting(true)
    setGrading(null)
    try {
      await post(`/api/practice/${submission.id}/regrade`, {})
      pollResult(submission.id)
    } catch (e: any) {
      setSubmitting(false)
      message.error(e.message || '重新批改失败')
    }
  }

  const mmss = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`

  const wordRange = examType === 'cet6' ? '150-200 词' : qType === 'small_writing' ? '约 100 词' : '约 150 词'

  return (
    <div className="page practice-page">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className="page-title">{isWriting ? '写作练习 · AI 批改' : '翻译练习 · AI 批改'}</h1>
          <div className="page-subtitle">
            {isWriting
              ? '六级短文写作 / 考研英语二应用文与图表作文 · 满分 15/10/15 分制'
              : '六级汉译英 / 考研英语二英译汉 · 真题满分 15 分制'}
          </div>
        </div>
        <Space wrap>
          <span style={{ fontSize: 13, color: '#888' }}>自由练习</span>
          <Switch checked={freeMode} onChange={setFreeMode} />
          <Button icon={<Badge count={history.length} size="small" offset={[-2, 2]}><ReloadOutlined /></Badge>}
                  onClick={() => { loadHistory().catch(() => {}); setHistoryOpen(true) }}>
            历史记录
          </Button>
        </Space>
      </div>

      {/* 筛选条 */}
      <div className="panel" style={{ marginBottom: 16, display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <Segmented
          options={[{ label: '六级', value: 'cet6' }, { label: '考研英语二', value: 'ky2' }]}
          value={examType}
          onChange={(v) => {
            setExamType(v as string); setYear(null)
            if (isWriting) setQType(v === 'cet6' ? 'writing' : 'small_writing')
          }}
        />
        {isWriting && examType === 'ky2' && (
          <Segmented
            options={[{ label: '应用文', value: 'small_writing' }, { label: '图表作文', value: 'big_writing' }]}
            value={qType}
            onChange={(v) => setQType(v as string)}
          />
        )}
        <Select
          allowClear placeholder="全部年份" style={{ minWidth: 130 }}
          value={year}
          options={(meta?.[examType]?.years || []).map((y: number) => ({ label: `${y} 年`, value: y }))}
          onChange={setYear}
        />
        <span style={{ color: '#bbb', fontSize: 13 }}>{questions.length} 套题目</span>
      </div>

      <div className="practice-layout">
        {/* 题目列表 / 自由练习 */}
        <div className="panel practice-list">
          {freeMode ? (
            <Space direction="vertical" style={{ width: '100%' }} size={10}>
              <Alert type="info" showIcon message="自由练习模式" description="粘贴任意段落/题目进行练习，批改按所选考试类型的评分标准执行。" />
              <Input placeholder="标题（可选）" value={freeTitle} onChange={(e) => setFreeTitle(e.target.value)} />
              <Input.TextArea
                placeholder={isWriting ? '粘贴作文题目要求…' : '粘贴翻译原文段落（六级为中文段 / 考研为英文段）…'}
                rows={12} value={freeSource} onChange={(e) => setFreeSource(e.target.value)}
              />
            </Space>
          ) : questions.length === 0 ? (
            <Empty description="没有符合条件的题目" />
          ) : (
            questions.map((q) => (
              <div
                key={q.id}
                onClick={() => { setCurrent(q); setSubmission(null); setGrading(null); setSeconds(0); setRunning(false) }}
                style={{
                  padding: '10px 12px', borderRadius: 8, cursor: 'pointer', marginBottom: 6,
                  background: current?.id === q.id ? '#eef3fb' : 'transparent',
                  border: current?.id === q.id ? '1px solid #c9d9f2' : '1px solid transparent',
                  transition: 'background .15s',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 13.5 }}>{q.title}</div>
                <div style={{ fontSize: 12, color: '#888', marginTop: 2, display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span>{Q_TYPE_LABEL[q.q_type]}</span>
                  {q.chart_image ? <span>· 含图表</span> : null}
                  {q.notes ? <span>· 补录</span> : null}
                  {(q as any).practice_count > 0 && <Tag color="green" style={{ marginRight: 0 }}>已练 {(q as any).practice_count}</Tag>}
                </div>
              </div>
            ))
          )}
        </div>

        {/* 题面 + 作答 */}
        <div className="practice-detail">
          {freeMode ? null : !current ? (
            <Empty description="请选择一套题目" style={{ marginTop: 80 }} />
          ) : (
            <div className="panel practice-question" style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <Space wrap>
                  <Tag color="blue">{current.title}</Tag>
                  <Tag>{Q_TYPE_LABEL[current.q_type]}</Tag>
                  {current.chart_image && <Tag color="purple">图表题</Tag>}
                </Space>
                <Space size={12}>
                  {countdownOn && (
                    <Button size="small" type={running ? 'primary' : 'default'} onClick={() => setRunning(!running)} danger={running && seconds > 30 * 60}>
                      {running ? '暂停' : seconds ? '继续' : '开始'} {mmss}
                    </Button>
                  )}
                  <span style={{ fontSize: 12, color: '#888' }}>计时</span>
                  <Switch size="small" checked={countdownOn} onChange={(v) => { setCountdownOn(v); if (!v) { setRunning(false); setSeconds(0) } }} />
                </Space>
              </div>
              {current.notes && <Alert type="info" showIcon message={current.notes} style={{ marginBottom: 12 }} />}
              {isWriting ? (
                <div className="source-text" style={{ marginBottom: 10 }}>{current.prompt}</div>
              ) : (
                <div className="source-text" style={{ marginBottom: 10 }}>{current.source_text}</div>
              )}
              {current.chart_image && (
                <div className="question-chart">
                  <img
                    src={`/data-static/${current.chart_display_image || current.chart_image}`}
                    alt={`${current.title} 图表原题`}
                  />
                  <Space style={{ display: 'flex', justifyContent: 'center', marginTop: 6 }} wrap>
                    <Button type="link" size="small" onClick={() => setChartPreview('clear')}>放大图表</Button>
                    {current.chart_original_image && <Button type="link" size="small" onClick={() => setChartPreview('original')}>查看原卷图表</Button>}
                  </Space>
                </div>
              )}
            </div>
          )}

          <div className="panel">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontWeight: 600 }}>我的作答</span>
              <Space size={14}>
                {isWriting && <span style={{ fontSize: 12.5, color: wordCount >= 150 && wordCount <= 200 ? '#52c41a' : '#999' }}>字数 {wordCount}（建议 {wordRange}）</span>}
                {!isWriting && <span style={{ fontSize: 12.5, color: '#999' }}>字数 {wordCount}</span>}
              </Space>
            </div>
            <Input.TextArea
              className="answer-area"
              rows={isWriting ? 12 : 8}
              placeholder={isWriting ? 'Write your essay here…（Ctrl+Enter 提交）' : examType === 'cet6' ? '在此输入英文译文…（Ctrl+Enter 提交）' : '在此输入中文译文…（Ctrl+Enter 提交）'}
              value={answer}
              onChange={(e) => updateAnswer(e.target.value)}
              onKeyDown={(e) => {
                if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); onSubmit() }
              }}
              disabled={submitting}
            />
            <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              {grading && !submitting && (
                <Button onClick={regrade} icon={<ReloadOutlined />}>重新批改</Button>
              )}
              <Button type="primary" icon={<SendOutlined />} loading={submitting} onClick={onSubmit}>
                提交批改
              </Button>
            </div>
            {submitting && (
              <Alert
                style={{ marginTop: 12 }} type="info" showIcon
                icon={<Spin size="small" />}
                message="AI 正在逐句批改，通常需要 20–60 秒…"
              />
            )}
          </div>

          {grading && (
            <div ref={resultRef} style={{ marginTop: 16 }}>
              <GradingResult grading={grading} />
            </div>
          )}
          {submission?.status === 'failed' && (
            <Alert style={{ marginTop: 16 }} type="error" showIcon
              message="批改失败" description={grading?.error || '请检查设置页的 AI 服务商配置'} />
          )}
        </div>
      </div>

      {/* 历史记录 */}
      <Modal title={chartPreview === 'original' ? '原卷图表' : '放大图表'} open={!!chartPreview}
        onCancel={() => setChartPreview(null)} footer={null} width={1100} destroyOnClose>
        {current?.chart_image && <img style={{ width: '100%', height: 'auto' }} alt={chartPreview === 'original' ? '原卷图表' : '清晰图表'}
          src={`/data-static/${chartPreview === 'original' ? current.chart_original_image : current.chart_display_image || current.chart_image}`} />}
      </Modal>
      <Modal title="练习历史" open={historyOpen} onCancel={() => setHistoryOpen(false)} footer={null} width={640}>
        <div style={{ maxHeight: '56vh', overflow: 'auto' }}>
          {history.length === 0 && <Empty description="暂无记录" />}
          {history.map((h) => (
            <div key={h.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 4px', borderBottom: '1px solid #f0f0f0' }}>
              <div>
                <div style={{ fontWeight: 500, fontSize: 13.5 }}>{h.title || '自由练习'}</div>
                <div style={{ fontSize: 12, color: '#999' }}>
                  {Q_TYPE_LABEL[h.q_type] || h.q_type} · {h.word_count} 词 · {h.created_at?.slice(5, 16)}
                </div>
              </div>
              <div>
                {h.score != null
                  ? <Statistic value={h.score} suffix={`/ ${h.full_score}`} valueStyle={{ fontSize: 16 }} />
                  : <Tag>{h.status}</Tag>}
              </div>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}
