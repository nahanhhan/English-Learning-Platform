import { ReloadOutlined, SendOutlined } from '@ant-design/icons'
import {
  Alert, Badge, Button, Empty, Input, Modal, Radio, Segmented, Select, Space,
  Statistic, Switch, Tag, message,
} from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, get, post, type Question, type Submission, type Grading } from '../api'
import GradingResult from '../components/GradingResult'
import ProviderSelect from '../components/ProviderSelect'
import GradingProgress from '../components/GradingProgress'

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
  const [questionsLoading, setQuestionsLoading] = useState(true)
  const [questionError, setQuestionError] = useState('')
  const [current, setCurrent] = useState<Question | null>(null)
  const [answer, setAnswer] = useState('')
  const [providerId, setProviderId] = useState<number>()
  const [freeMode, setFreeMode] = useState(false)
  const [freeSource, setFreeSource] = useState('')
  const [freeTitle, setFreeTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [pending, setPending] = useState<{ id: number; draft: string; content: string }>()
  const [pollError, setPollError] = useState(false)
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
  const submissionLock = useRef(false)

  // 草稿自动保存：按题目区分，自由练习独立保存
  const draftKey = freeMode ? 'elp:draft:free' : `elp:draft:q${current?.id ?? 0}`

  const loadQuestions = useCallback(async () => {
    const request = ++questionRequest.current
    const params = new URLSearchParams({ exam_type: examType, q_type: qType })
    if (year) params.set('year', String(year))
    setQuestionsLoading(true)
    setQuestionError('')
    try {
      const data = await get<Question[]>(`/api/questions?${params}`)
      if (request !== questionRequest.current) return
      setQuestions(data)
      setCurrent((c) => (c && data.find((d) => d.id === c.id)) || data[0] || null)
      setSubmission(null)
      setGrading(null)
    } catch (error) {
      if (request === questionRequest.current) setQuestionError(error instanceof Error ? error.message : '请稍后重试')
    } finally {
      if (request === questionRequest.current) setQuestionsLoading(false)
    }
  }, [examType, qType, year])

  useEffect(() => {
    get('/api/questions/meta').then(setMeta).catch(() => {})
  }, [])

  useEffect(() => {
    void loadQuestions()
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

  useEffect(() => {
    if (!pending) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const data = await api<{ submission: Submission; grading: Grading | null }>(`/api/practice/${pending.id}`, {
          signal: controller.signal,
        })
        if (controller.signal.aborted) return
        setPollError(false)
        setSubmission(data.submission)
        if (data.submission.status === 'pending' || data.submission.status === 'grading') {
          timer = setTimeout(poll, 1500)
          return
        }
        setGrading(data.grading)
        setPending(undefined)
        submissionLock.current = false
        setSubmitting(false)
        setRunning(false)
        void loadHistory().catch(() => {})
        if (data.submission.status === 'done') {
          try {
            if (localStorage.getItem(pending.draft)?.trim() === pending.content) localStorage.removeItem(pending.draft)
          } catch { /* 浏览器不允许访问草稿时仍展示结果。 */ }
        }
      } catch {
        if (controller.signal.aborted) return
        setPollError(true)
        timer = setTimeout(poll, 4000)
      }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [pending, loadHistory])

  useEffect(() => {
    if (submission?.status === 'done' && grading) {
      resultRef.current?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
        block: 'start',
      })
    }
  }, [submission?.status, grading])

  const onSubmit = async () => {
    if (submissionLock.current || (!freeMode && (!current || questionsLoading || questionError))) return
    const content = answer.trim()
    if (!content) return message.warning('请先输入你的作答')
    if (freeMode && !freeSource.trim()) return message.warning('自由练习请在左侧粘贴原文段落')
    submissionLock.current = true
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
      const resp = await post<{ submission_id: number }>('/api/practice/submit', { ...body, provider_id: providerId })
      setPending({ id: resp.submission_id, draft: draftKey, content })
    } catch (e: any) {
      submissionLock.current = false
      setSubmitting(false)
      message.error(e.message || '提交失败')
    }
  }

  const regrade = async () => {
    if (!submission || submissionLock.current) return
    submissionLock.current = true
    setSubmitting(true)
    setGrading(null)
    try {
      await post(`/api/practice/${submission.id}/regrade`, { provider_id: providerId })
      setPending({ id: submission.id, draft: draftKey, content: submission.content.trim() })
    } catch (e: any) {
      submissionLock.current = false
      setSubmitting(false)
      message.error(e.message || '重新批改失败')
    }
  }

  const mmss = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`

  const wordRange = examType === 'cet6' ? '150-200 词' : qType === 'small_writing' ? '约 100 词' : '约 150 词'

  return (
    <div className="page practice-page">
      <header className="page-heading">
        <div>
          <h1 className="page-title">{isWriting ? '写作练习' : '真题翻译'}</h1>
          <div className="page-subtitle">
            {isWriting
              ? '六级短文写作 / 考研英语二应用文与图表作文 · 满分 15/10/15 分制'
              : '六级汉译英 / 考研英语二英译汉 · 真题满分 15 分制'}
          </div>
        </div>
        <Space wrap>
          <span style={{ fontSize: 13, color: 'var(--workspace-muted)' }}>自由练习</span>
          <Switch aria-label="自由练习" checked={freeMode} disabled={submitting} onChange={value => {
            setFreeMode(value)
            setSubmission(null)
            setGrading(null)
          }} />
          <Button icon={<Badge count={history.length} size="small" offset={[-2, 2]}><ReloadOutlined /></Badge>}
                  onClick={() => { loadHistory().catch(() => {}); setHistoryOpen(true) }}>
            历史记录
          </Button>
        </Space>
      </header>

      {/* 筛选条 */}
      <div className="panel practice-filters">
        <Segmented
          options={[{ label: '六级', value: 'cet6' }, { label: '考研英语二', value: 'ky2' }]}
          value={examType}
          disabled={submitting}
          onChange={(v) => {
            setExamType(v as string); setYear(null)
            if (isWriting) setQType(v === 'cet6' ? 'writing' : 'small_writing')
          }}
        />
        {isWriting && examType === 'ky2' && (
          <Segmented
            options={[{ label: '应用文', value: 'small_writing' }, { label: '图表作文', value: 'big_writing' }]}
            value={qType}
            disabled={submitting}
            onChange={(v) => setQType(v as string)}
          />
        )}
        <Select
          aria-label="真题年份" allowClear placeholder="全部年份" style={{ minWidth: 130 }}
          value={year}
          disabled={submitting || freeMode}
          options={(meta?.[examType]?.years || []).map((y: number) => ({ label: `${y} 年`, value: y }))}
          onChange={setYear}
        />
        {!freeMode && <span className="practice-count" role="status">{questionsLoading ? '正在筛选题目…' : questionError ? '题目暂不可用' : `${questions.length} 套题目`}</span>}
      </div>

      <div className="practice-layout">
        {/* 题目列表 / 自由练习 */}
        <section className="panel practice-list" aria-label={freeMode ? '自由练习题面' : '题目列表'}>
          <h2>{freeMode ? '自选题面' : '题目列表'}</h2>
          {freeMode ? (
            <Space direction="vertical" style={{ width: '100%' }} size={10}>
              <Alert type="info" showIcon message="自由练习模式" description="粘贴任意段落/题目进行练习，批改按所选考试类型的评分标准执行。" />
              <Input placeholder="标题（可选）" value={freeTitle} onChange={(e) => setFreeTitle(e.target.value)} />
              <Input.TextArea
                placeholder={isWriting ? '粘贴作文题目要求…' : '粘贴翻译原文段落（六级为中文段 / 考研为英文段）…'}
                rows={12} value={freeSource} onChange={(e) => setFreeSource(e.target.value)}
              />
            </Space>
          ) : questionError ? (
            <Alert type="error" message="题目加载失败" description={questionError}
              action={<Button size="small" onClick={() => void loadQuestions()}>重试</Button>} />
          ) : questionsLoading ? (
            <p className="practice-count" role="status">正在读取题目…</p>
          ) : questions.length === 0 ? (
            <Empty description="没有符合条件的题目" />
          ) : (
            questions.map((q) => (
              <button type="button"
                key={q.id}
                className="practice-item"
                aria-pressed={current?.id === q.id}
                disabled={submitting}
                onClick={() => { setCurrent(q); setSubmission(null); setGrading(null); setSeconds(0); setRunning(false) }}
              >
                <span className="practice-item-title">{q.title}</span>
                <span className="practice-item-meta">
                  <span>{Q_TYPE_LABEL[q.q_type]}</span>
                  {q.chart_image ? <span>· 含图表</span> : null}
                  {q.notes ? <span>· 补录</span> : null}
                  {!!q.practice_count && <Tag color="green" style={{ marginRight: 0 }}>已练 {q.practice_count}</Tag>}
                </span>
              </button>
            ))
          )}
        </section>

        {/* 题面 + 作答 */}
        <div className="practice-detail">
          <div className={freeMode ? 'practice-workspace practice-workspace-single' : 'practice-workspace'}>
            {freeMode ? null : questionsLoading || questionError || !current ? (
              <div className="panel practice-count">{questionsLoading ? '正在读取题面…' : questionError ? '题面将在重试后显示' : '请选择一套题目'}</div>
            ) : (
              <div className="panel practice-question" key={current.id}>
                <h2>{current.title}</h2>
                <div className="practice-question-heading">
                  <Space wrap>
                    <Tag>{Q_TYPE_LABEL[current.q_type]}</Tag>
                    {current.chart_image && <Tag color="purple">图表题</Tag>}
                  </Space>
                  <Space size={12}>
                    {countdownOn && (
                      <Button size="small" type={running ? 'primary' : 'default'} onClick={() => setRunning(!running)} danger={running && seconds > 30 * 60}>
                        {running ? '暂停' : seconds ? '继续' : '开始'} {mmss}
                      </Button>
                    )}
                    <span style={{ fontSize: 12, color: 'var(--workspace-muted)' }}>计时</span>
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

            <div className="panel practice-answer">
              <div className="practice-question-heading">
                <h2>我的作答</h2>
                <Space size={14}>
                  {isWriting && <span style={{ fontSize: 12.5, color: wordCount >= 150 && wordCount <= 200 ? 'var(--workspace-success)' : 'var(--workspace-subtle)' }}>字数 {wordCount}（建议 {wordRange}）</span>}
                  {!isWriting && <span style={{ fontSize: 12.5, color: 'var(--workspace-subtle)' }}>字数 {wordCount}</span>}
                </Space>
              </div>
              <Input.TextArea
                className="answer-area"
                aria-label="我的作答"
                rows={isWriting ? 12 : 8}
                placeholder={isWriting ? 'Write your essay here…（Ctrl+Enter 提交）' : examType === 'cet6' ? '在此输入英文译文…（Ctrl+Enter 提交）' : '在此输入中文译文…（Ctrl+Enter 提交）'}
                value={answer}
                onChange={(e) => updateAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.ctrlKey && e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); void onSubmit() }
                }}
                disabled={submitting || (!freeMode && (!current || questionsLoading || !!questionError))}
              />
              <div className="practice-provider"><ProviderSelect value={providerId} onChange={setProviderId} disabled={submitting} /></div>
              <div className="practice-submit">
                {(grading || submission?.status === 'failed') && !submitting && (
                  <Button onClick={regrade} icon={<ReloadOutlined />}>重新批改</Button>
                )}
                <Button type="primary" icon={<SendOutlined />} loading={submitting} onClick={onSubmit}
                  disabled={!answer.trim() || (!freeMode && (!current || questionsLoading || !!questionError))}>
                  提交批改
                </Button>
              </div>
              {submitting && <GradingProgress />}
              {pollError && <Alert type="warning" showIcon message="暂时无法读取批改进度，正在重试。作答已保存。" />}
            </div>
          </div>

          {grading && submission?.status === 'done' && (
            <div ref={resultRef} className="practice-feedback">
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
            <div key={h.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 4px', borderBottom: '1px solid var(--workspace-line)' }}>
              <div>
                <div style={{ fontWeight: 500, fontSize: 13.5 }}>{h.title || '自由练习'}</div>
                <div style={{ fontSize: 12, color: 'var(--workspace-subtle)' }}>
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
