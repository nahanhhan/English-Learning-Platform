import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  type InputRef,
  Modal,
  Radio,
  Segmented,
  Select,
  Space,
  Statistic,
  Tag,
  Tooltip,
  message,
} from 'antd'
import { Check, Plus, Search, Star, Volume2, X, Zap } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { get, post, type BookProgress, type StudyCard } from '../api'
import AmericanPhonetic from '../components/AmericanPhonetic'
import AppIcon from '../components/AppIcon'
import PartOfSpeech from '../components/PartOfSpeech'
import VolumeControl from '../components/VolumeControl'
import { cancelPendingSpeech, speak, stopSpeaking } from '../speak'

function AccentButtons({ word }: { word: string }) {
  const [activeAccent, setActiveAccent] = useState<'uk' | 'us' | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => () => clearTimeout(timerRef.current), [])

  const triggerSpeak = (accent: 'uk' | 'us', event: React.MouseEvent) => {
    event.stopPropagation()
    clearTimeout(timerRef.current)
    setActiveAccent(accent)
    timerRef.current = setTimeout(() => setActiveAccent(null), 700)
    void speak(word, accent)
  }

  return (
    <span style={{ display: 'inline-flex', gap: 8, verticalAlign: 'middle' }}>
      <Button
        size="small"
        className={`ap-accent-btn ap-press${activeAccent === 'uk' ? ' speaking-pulse' : ''}`}
        style={activeAccent === 'uk' ? { borderColor: 'var(--workspace-accent)', color: 'var(--workspace-accent)' } : undefined}
        icon={<AppIcon icon={Volume2} size={13} />}
        onClick={e => triggerSpeak('uk', e)}
      >
        英
      </Button>
      <Button
        size="small"
        className={`ap-accent-btn ap-press${activeAccent === 'us' ? ' speaking-pulse' : ''}`}
        style={activeAccent === 'us' ? { borderColor: 'var(--workspace-accent)', color: 'var(--workspace-accent)' } : undefined}
        icon={<AppIcon icon={Volume2} size={13} />}
        onClick={e => triggerSpeak('us', e)}
      >
        美
      </Button>
    </span>
  )
}

type Tab = 'study' | 'mistake' | 'quiz' | 'browse'
type Stage = 'choice' | 'spell' | 'done'
type Source = 'normal' | 'mistake'

const RATING_LABEL: Record<string, { text: string; color: string }> = {
  good: { text: '回答正确 · 认识', color: 'var(--workspace-success)' },
  hard: { text: '拼写有误 · 模糊', color: 'var(--workspace-warning)' },
  again: { text: '回答错误 · 不认识', color: 'var(--workspace-error)' },
}

function isWord(itemType: string) {
  return itemType === 'word'
}

export default function Study({ itemType }: { itemType: 'word' | 'phrase' }) {
  const [books, setBooks] = useState<BookProgress[]>([])
  const [book, setBook] = useState<string>('')
  const [tab, setTab] = useState<Tab>('study')

  // 学习流
  const [source, setSource] = useState<Source>('normal')
  const [queue, setQueue] = useState<{ review: StudyCard[]; new: StudyCard[]; counts: any } | null>(null)
  const [queueIdx, setQueueIdx] = useState(0)
  const [stage, setStage] = useState<Stage>('choice')
  const [picked, setPicked] = useState<string | null>(null)
  const [choiceRight, setChoiceRight] = useState(false)
  const [spellInput, setSpellInput] = useState('')
  const [spellWrong, setSpellWrong] = useState(false)
  const spellInputRef = useRef<InputRef>(null)
  const [cardResult, setCardResult] = useState<StudyCard | null>(null)
  const [locked, setLocked] = useState(false)
  const [sessionDone, setSessionDone] = useState(0)
  const advanceRef = useRef<any>(null)

  // 自动发音
  const [autoSpeak, setAutoSpeak] = useState(false)
  const queueSeqRef = useRef(0)
  const queueLoadingRef = useRef(false)
  const queueGenRef = useRef(0)
  const spokenKeyRef = useRef('')

  // 测验
  const [quiz, setQuiz] = useState<any[]>([])
  const [quizIdx, setQuizIdx] = useState(0)
  const [quizPicked, setQuizPicked] = useState<string | null>(null)
  const [quizRight, setQuizRight] = useState(0)
  const [quizLoading, setQuizLoading] = useState(false)

  // 错题本
  const [mistakes, setMistakes] = useState<StudyCard[]>([])

  // 词表
  const [browseData, setBrowseData] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [customOpen, setCustomOpen] = useState(false)
  const [customForm, setCustomForm] = useState({ headword: '', translation: '' })

  const isW = isWord(itemType)
  const nameOf = (b: string) =>
    b === 'cet6' ? '六级核心词' : b === 'kaoyan' ? '考研核心词' : b === 'exam' ? '考试短语' : '我的收藏'

  const loadBooks = useCallback(async () => {
    const data = await get<BookProgress[]>(isW ? '/api/vocab/books?item_type=word' : '/api/phrases/books')
    setBooks(data)
    setBook(b => (b && data.find(d => d.book === b) ? b : data[0]?.book || ''))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isW])

  useEffect(() => {
    loadBooks().catch(e => message.error(e.message))
  }, [loadBooks])

  const loadMistakes = useCallback(async () => {
    const url = isW ? `/api/vocab/mistakes?book=${book}&item_type=word` : `/api/phrases/mistakes?book=${book}`
    setMistakes(await get(url))
  }, [book, isW])

  useEffect(() => {
    if (book) loadMistakes().catch(() => {})
  }, [book, loadMistakes])

  const loadQueue = useCallback(
    async (src: Source = source) => {
      if (!book) return
      stopSpeaking()
      const seq = ++queueSeqRef.current
      queueLoadingRef.current = true
      resetCardState()
      setQueueIdx(0)
      const base = isW ? `/api/vocab/queue?book=${book}&item_type=word` : `/api/phrases/queue?book=${book}`
      try {
        const data = await get(`${base}&source=${src}`)
        if (seq !== queueSeqRef.current) return
        queueLoadingRef.current = false
        queueGenRef.current += 1
        setQueue(data)
      } catch (e) {
        if (seq === queueSeqRef.current) queueLoadingRef.current = false
        throw e
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    },
    [book, isW, source],
  )

  useEffect(() => {
    if (tab === 'study') loadQueue().catch(e => message.error(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, loadQueue])

  function resetCardState() {
    setStage('choice')
    setPicked(null)
    setChoiceRight(false)
    setSpellInput('')
    setSpellWrong(false)
    setCardResult(null)
    setLocked(false)
    if (advanceRef.current) {
      clearTimeout(advanceRef.current)
      advanceRef.current = null
    }
  }

  const cards = useMemo(() => {
    if (!queue) return []
    return [...queue.review, ...queue.new]
  }, [queue])
  const currentCard = cards[queueIdx]

  useEffect(() => {
    let alive = true
    get('/api/settings')
      .then(d => {
        if (alive) setAutoSpeak(d?.prefs?.auto_speak !== '0')
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    stopSpeaking()
  }, [book, tab, currentCard?.card_id, quizIdx, page, search, statusFilter, customOpen])
  useEffect(() => {
    cancelPendingSpeech()
  }, [stage])

  useEffect(() => {
    if (tab !== 'study' || stage !== 'choice') return
    if (!autoSpeak || queueLoadingRef.current || !currentCard) return
    const key = `${queueGenRef.current}:${queueIdx}`
    if (spokenKeyRef.current === key) return
    spokenKeyRef.current = key
    speak(currentCard.headword || currentCard.text || '', 'us')
  }, [tab, stage, currentCard, queueIdx, autoSpeak])

  useEffect(() => {
    if (tab !== 'study') stopSpeaking()
  }, [tab])

  useEffect(() => () => stopSpeaking(), [])

  const nextCard = useCallback(async () => {
    if (advanceRef.current) {
      clearTimeout(advanceRef.current)
      advanceRef.current = null
    }
    if (queueIdx + 1 >= cards.length) {
      const base = isW ? `/api/vocab/queue?book=${book}&item_type=word` : `/api/phrases/queue?book=${book}`
      const data = await get(`${base}&source=${source}`)
      setQueue(data)
      setQueueIdx(0)
      resetCardState()
      if (!data.review.length && !data.new.length) {
        message.success(source === 'mistake' ? '错题专项练习完成！' : '今日学习任务完成，明天再来复习吧！🎉')
        loadBooks()
        loadMistakes()
        if (source === 'mistake') setTab('mistake')
      }
    } else {
      setQueueIdx(i => i + 1)
      resetCardState()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queueIdx, cards.length, book, isW, source, loadBooks, loadMistakes])

  const finishCard = useCallback(
    async (rating: 'good' | 'hard' | 'again') => {
      if (!currentCard) return
      try {
        const resp = await post<StudyCard>(isW ? '/api/vocab/answer' : '/api/phrases/answer', {
          card_id: currentCard.card_id,
          rating,
        })
        setSessionDone(s => s + 1)
        setCardResult(resp)
        setStage('done')
        loadMistakes().catch(() => {})
        if (rating === 'good') {
          advanceRef.current = setTimeout(() => nextCard(), 1000)
        }
      } catch (e: any) {
        message.error(e.message)
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    },
    [currentCard, isW, nextCard, loadMistakes],
  )

  const pick = (opt: string) => {
    if (!currentCard || locked || stage !== 'choice') return
    setLocked(true)
    setPicked(opt)
    const right = opt === currentCard.answer
    setChoiceRight(right)
    setTimeout(() => {
      if (isW) {
        setStage('spell')
      } else {
        finishCard(right ? 'good' : 'again')
      }
    }, 950)
  }

  const spellHint = useMemo(() => {
    const w = currentCard?.headword || ''
    return w
      .split('')
      .map((ch, i) => (i === 0 || !/[a-zA-Z]/.test(ch) ? ch : '_'))
      .join(' ')
  }, [currentCard])

  const submitSpell = () => {
    const target = (currentCard?.headword || '').trim()
    const ok = spellInput.trim().toLowerCase() === target.toLowerCase()
    if (!ok) {
      setSpellWrong(true)
      setSpellInput('')
      spellInputRef.current?.focus({ preventScroll: true })
      return
    }
    if (!choiceRight) finishCard('again')
    else if (spellWrong) finishCard('hard')
    else finishCard('good')
  }

  // 键盘：1-4 选择；Enter 提交拼写 / 下一张
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (document.querySelector('#workspace-page-jump, .ant-modal-open')) return
      const el = (e.target as HTMLElement)?.tagName
      if (tab !== 'study' || el === 'INPUT' || el === 'TEXTAREA') return
      if (stage === 'choice' && currentCard && ['1', '2', '3', '4'].includes(e.key)) {
        const idx = Number(e.key) - 1
        const opts = currentCard.options || []
        if (idx < opts.length) pick(opts[idx])
      }
      if (stage === 'spell' && e.key === 'Enter') submitSpell()
      if (stage === 'done' && e.key === 'Enter') {
        const rating = choiceRight ? (spellWrong ? 'hard' : 'good') : 'again'
        if (rating !== 'good') nextCard()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const loadQuiz = async () => {
    setQuizLoading(true)
    try {
      const url = isW ? `/api/vocab/quiz?book=${book}&count=10` : `/api/phrases/quiz?book=${book}&count=10`
      const data = await get(url)
      setQuiz(data)
      setQuizIdx(0)
      setQuizPicked(null)
      setQuizRight(0)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setQuizLoading(false)
    }
  }

  useEffect(() => {
    if (tab === 'quiz' && book) loadQuiz()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, book])

  const loadBrowse = useCallback(async () => {
    if (!book) return
    const params = new URLSearchParams({ book, page: String(page), page_size: '30', status: statusFilter })
    if (search.trim()) params.set('search', search.trim())
    const url = isW ? `/api/vocab/browse?item_type=word&${params}` : `/api/phrases/browse?${params}`
    setBrowseData(await get(url))
  }, [book, page, statusFilter, search, isW])

  useEffect(() => {
    if (tab === 'browse') loadBrowse().catch(e => message.error(e.message))
  }, [tab, loadBrowse])

  const toggleStar = async (cardId: number) => {
    await post(isW ? '/api/vocab/star' : '/api/phrases/star', { card_id: cardId })
    loadBrowse().catch(() => {})
  }

  const addCustom = async () => {
    try {
      if (isW) await post('/api/vocab/custom', { headword: customForm.headword, translation: customForm.translation })
      else await post('/api/phrases/custom', { text: customForm.headword, translation: customForm.translation })
      message.success('已添加')
      setCustomOpen(false)
      setCustomForm({ headword: '', translation: '' })
      loadBooks()
      if (tab === 'browse') loadBrowse()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const bookInfo = books.find(b => b.book === book)
  const totalQueue = queue ? queue.counts.review + queue.counts.new : 0

  const renderStudy = () => {
    if (!queue || (!totalQueue && !cards.length)) {
      return (
        <Empty
          description={source === 'mistake' ? '错题本已清空 🎉' : '今日队列已清空，休息一下 ☕'}
          style={{ marginTop: 60 }}
        />
      )
    }
    if (!currentCard) return <Empty description="加载中…" style={{ marginTop: 60 }} />

    const progressPct = Math.round((queueIdx / Math.max(cards.length, 1)) * 100)

    return (
      <>
        <div className="study-question-meta">
          <Space size={6} wrap>
            {source === 'mistake' ? <Tag color="red">错题专项</Tag> : <Tag color="blue">今日队列</Tag>}
            {currentCard.status === 'new' ? <Tag color="geekblue">新词</Tag> : <Tag color="orange">复习</Tag>}
            {currentCard.in_mistake_book && <Tag color="volcano">错题连对 {currentCard.mistake_consec}/3</Tag>}
          </Space>
          <span className="ap-num" style={{ color: 'var(--workspace-subtle)', fontSize: 12.5 }}>
            {queueIdx + 1} / {cards.length} · 本轮完成 {sessionDone}
          </span>
        </div>

        <div
          className="study-progress-track"
          role="progressbar"
          aria-label="本轮学习进度"
          aria-valuemin={0}
          aria-valuemax={Math.max(cards.length, 1)}
          aria-valuenow={queueIdx}
        >
          <div className="study-progress-fill ap-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>

        {stage === 'choice' && (
          <Card key={currentCard.card_id} className="study-practice-card ap-vocab-card anim-card-swap">
            <div className="study-prompt">
              <div className="study-headword">
                {currentCard.headword || currentCard.text}
                {isW && <PartOfSpeech value={currentCard.part_of_speech} />}
              </div>
              {isW && <AmericanPhonetic value={currentCard.phonetic_us} />}
              <div style={{ marginTop: 8, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                <AccentButtons word={currentCard.headword || currentCard.text || ''} />
              </div>
              <div style={{ color: 'var(--workspace-subtle)', fontSize: 12.5, marginTop: 10 }}>
                选择正确的{isW ? '中文释义' : '释义'}（快捷键 1-4）
              </div>
            </div>

            <div className="practice-options">
              {(currentCard.options || []).map((opt, i) => {
                const isPicked = picked === opt
                const isAnswer = opt === currentCard.answer
                const classes = ['ap-vocab-opt']
                if (!picked) {
                  classes.push('is-idle')
                } else if (isAnswer) {
                  classes.push('is-correct')
                  if (isPicked) classes.push('anim-option-pop')
                } else if (isPicked) {
                  classes.push('is-wrong', 'anim-wrong-shake')
                } else {
                  classes.push('is-dimmed')
                }

                return (
                  <button
                    key={opt + i}
                    type="button"
                    disabled={!!picked}
                    className={classes.join(' ')}
                    onClick={() => pick(opt)}
                  >
                    <span className="ap-vocab-opt-main">
                      <span className="ap-vocab-keycap">{i + 1}</span>
                      <span className="ap-vocab-opt-label">{opt}</span>
                    </span>
                    {picked && isAnswer && (
                      <span
                        className="ap-vocab-opt-status anim-check-spring"
                        style={{ color: 'var(--workspace-success)' }}
                      >
                        <AppIcon icon={Check} size={17} strokeWidth={2.4} />
                      </span>
                    )}
                    {picked && isPicked && !isAnswer && (
                      <span className="ap-vocab-opt-status" style={{ color: 'var(--workspace-error)' }}>
                        <AppIcon icon={X} size={17} strokeWidth={2.4} />
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </Card>
        )}

        {stage === 'spell' && (
          <Card key={`${currentCard.card_id}-spell`} className="study-practice-card ap-vocab-card anim-card-swap">
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {currentCard.answer}
              </div>
              <div style={{ marginTop: 8, display: 'flex', justifyContent: 'center' }}>
                <AccentButtons word={currentCard.headword || ''} />
              </div>
              <div style={{ color: 'var(--workspace-subtle)', fontSize: 13, marginTop: 8 }}>
                {choiceRight ? '拼写这个单词' : '选择有误，拼写一下加深记忆'}
              </div>
              <div
                style={{
                  marginTop: 10,
                  fontSize: 18,
                  letterSpacing: 4,
                  color: 'var(--workspace-accent)',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                }}
              >
                {spellWrong ? currentCard.headword : spellHint}
                <PartOfSpeech value={currentCard.part_of_speech} />
              </div>
            </div>

            <Space.Compact style={{ width: '100%', maxWidth: 420, display: 'flex', margin: '0 auto' }}>
              <Input
                ref={spellInputRef}
                size="large"
                aria-label="英文拼写"
                placeholder={spellWrong ? `正确拼写：${currentCard.headword}（重打一遍）` : '输入拼写后回车'}
                value={spellInput}
                autoFocus
                onChange={e => setSpellInput(e.target.value)}
                onPressEnter={submitSpell}
                status={spellWrong ? 'error' : undefined}
              />
              <Button size="large" type="primary" onClick={submitSpell}>
                提交
              </Button>
            </Space.Compact>

            {spellWrong && (
              <div style={{ textAlign: 'center', marginTop: 12 }}>
                <Tag color="red">拼写错误</Tag>
                <span style={{ fontSize: 13.5 }}>请按提示重打一遍正确拼写，本词已计入错题本</span>
              </div>
            )}
          </Card>
        )}

        {stage === 'done' &&
          cardResult &&
          (() => {
            const rating = choiceRight ? (spellWrong ? 'hard' : 'good') : 'again'
            const meta = RATING_LABEL[rating]
            const enteredBook = cardResult.in_mistake_book && !currentCard.in_mistake_book
            const removedBook = !cardResult.in_mistake_book && currentCard.in_mistake_book
            return (
              <Card
                key={`${currentCard.card_id}-done`}
                className="study-practice-card ap-vocab-card anim-card-swap"
                style={{ textAlign: 'center' }}
              >
                <div style={{ fontSize: 40, marginBottom: 8 }}>
                  {rating === 'good' ? '🎉' : rating === 'hard' ? '😅' : '💪'}
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: meta.color, marginBottom: 6 }}>
                  {meta.text}
                </div>
                <div style={{ color: 'var(--workspace-muted)', fontSize: 14 }}>
                  <b>{currentCard.headword || currentCard.text}</b>
                  {isW && <PartOfSpeech value={currentCard.part_of_speech} />}
                  <span style={{ margin: '0 8px', color: 'var(--workspace-strong-line)' }}>|</span>
                  {currentCard.answer}
                </div>
                <div style={{ marginTop: 10 }}>
                  {removedBook && <Tag color="green">连对 3 次，已移出错题本 🎉</Tag>}
                  {enteredBook && <Tag color="volcano">已加入错题本</Tag>}
                  {!enteredBook && !removedBook && cardResult.in_mistake_book && (
                    <Tag color="orange">错题连对 {cardResult.mistake_consec}/3</Tag>
                  )}
                </div>
                {rating !== 'good' && (
                  <Button type="primary" style={{ marginTop: 18 }} onClick={nextCard}>
                    下一张（Enter）
                  </Button>
                )}
              </Card>
            )
          })()}

        <div style={{ textAlign: 'center', color: 'var(--workspace-subtle)', fontSize: 12.5, marginTop: 12 }}>
          {isW ? '快捷键：1-4 选择 · Enter 提交拼写/下一张' : '快捷键：1-4 选择 · 答对自动进入下一张'}
        </div>
      </>
    )
  }

  return (
    <div className="page study-page">
      <header className="page-heading study-toolbar ap-stagger" style={{ '--stagger-i': 0 } as CSSProperties}>
        <div>
          <h1 className="page-title">{isW ? '背单词' : '背短语'}</h1>
          <div className="page-subtitle">
            四选一选择{isW ? ' + 拼写强化' : ''} · 答错自动进入错题本，连对 3 次移出
          </div>
        </div>
        <Space wrap size={10}>
          <VolumeControl />
          <Select
            aria-label={isW ? '单词词书' : '短语词书'}
            style={{ minWidth: 160 }}
            value={book}
            options={books.map(b => ({ label: nameOf(b.book), value: b.book }))}
            onChange={setBook}
          />
          <Button icon={<AppIcon icon={Plus} size={15} />} onClick={() => setCustomOpen(true)}>
            添加{isW ? '单词' : '短语'}
          </Button>
        </Space>
      </header>

      <div className="study-stats ap-stagger" style={{ '--stagger-i': 1 } as CSSProperties}>
        <div className="ap-card study-stat-card">
          <span className="study-stat-label">词库总量</span>
          <span className="study-stat-value">{bookInfo?.total_items ?? 0}</span>
        </div>
        <div className="ap-card study-stat-card">
          <span className="study-stat-label">已开始学习</span>
          <span className="study-stat-value" style={{ color: 'var(--workspace-accent)' }}>
            {bookInfo?.started ?? 0}
          </span>
        </div>
        <div className="ap-card study-stat-card">
          <span className="study-stat-label">已掌握</span>
          <span className="study-stat-value" style={{ color: 'var(--workspace-success)' }}>
            {bookInfo?.mastered ?? 0}
          </span>
        </div>
        <div className="ap-card study-stat-card">
          <span className="study-stat-label">错题本</span>
          <span
            className="study-stat-value"
            style={{ color: mistakes.length ? 'var(--workspace-error)' : undefined }}
          >
            {mistakes.length}
          </span>
        </div>
      </div>

      <div className="ap-stagger" style={{ '--stagger-i': 2, marginBottom: 10 } as CSSProperties}>
        <Segmented
          options={[
            {
              label: (
                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                  学习
                  {totalQueue > 0 && source === 'normal' && (
                    <span
                      className="ap-seg-badge"
                      style={{ background: 'var(--workspace-accent-bg)', color: 'var(--workspace-accent)' }}
                    >
                      {totalQueue}
                    </span>
                  )}
                </span>
              ),
              value: 'study',
            },
            {
              label: (
                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                  错题本
                  {mistakes.length > 0 && (
                    <span
                      className="ap-seg-badge"
                      style={{ background: 'var(--workspace-error-bg)', color: 'var(--workspace-error)' }}
                    >
                      {mistakes.length}
                    </span>
                  )}
                </span>
              ),
              value: 'mistake',
            },
            { label: '测验', value: 'quiz' },
            { label: '词表', value: 'browse' },
          ]}
          value={tab}
          onChange={v => {
            const t = v as Tab
            setTab(t)
            if (t === 'mistake') loadMistakes().catch(() => {})
          }}
        />
      </div>

      {tab === 'study' && (
        <div className="study-practice">
          {source === 'mistake' && (
            <div style={{ textAlign: 'center', marginBottom: 10 }}>
              <Button
                size="small"
                onClick={async () => {
                  setSource('normal')
                  await loadQueue('normal')
                }}
              >
                退出专项练习，回到今日队列
              </Button>
            </div>
          )}
          {renderStudy()}
        </div>
      )}

      {tab === 'mistake' && (
        <div style={{ maxWidth: 740, margin: '0 auto' }} className="anim-card-swap">
          <Card size="small" style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <span style={{ color: 'var(--workspace-muted)', fontSize: 13.5 }}>
                答错即进入错题本；连对 <b>3</b> 次（单词需选择与拼写都正确）自动移出。
              </span>
              <Button
                type="primary"
                danger
                disabled={mistakes.length === 0}
                icon={<AppIcon icon={Zap} size={14} />}
                onClick={async () => {
                  setSource('mistake')
                  setTab('study')
                  await loadQueue('mistake')
                }}
              >
                开始专项练习{mistakes.length ? `（${mistakes.length} 题）` : ''}
              </Button>
            </div>
          </Card>
          <Card size="small">
            {mistakes.length === 0 ? (
              <Empty description="错题本已清空 🎉" style={{ margin: '24px 0' }} />
            ) : (
              mistakes.map(m => (
                <div
                  key={m.card_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '11px 6px',
                    borderBottom: '1px solid var(--workspace-line)',
                  }}
                >
                  <span style={{ minWidth: 140, fontWeight: 600 }}>
                    {m.headword || m.text}
                    {isW && <PartOfSpeech value={m.part_of_speech} />}
                  </span>
                  <span style={{ flex: 1, color: 'var(--workspace-muted)', fontSize: 13.5 }}>
                    {m.translation?.split('\n')[0]}
                  </span>
                  <span className="ap-num" style={{ fontSize: 12.5 }}>
                    {[0, 1, 2].map(i => (
                      <span
                        key={i}
                        style={{
                          display: 'inline-block',
                          width: 9,
                          height: 9,
                          borderRadius: '50%',
                          marginRight: 4,
                          background:
                            (m.mistake_consec || 0) > i ? 'var(--workspace-success)' : 'var(--workspace-raised)',
                        }}
                      />
                    ))}
                    <span style={{ color: 'var(--workspace-subtle)', marginLeft: 6 }}>
                      连对 {m.mistake_consec}/3
                    </span>
                  </span>
                </div>
              ))
            )}
          </Card>
        </div>
      )}

      {tab === 'quiz' && (
        <div style={{ maxWidth: 680, margin: '0 auto' }} className="anim-card-swap">
          {quizLoading ? (
            <Empty description="出题中…" />
          ) : quiz.length === 0 ? (
            <Empty description="先去学习几个词再来测验吧" style={{ marginTop: 60 }} />
          ) : quizIdx >= quiz.length ? (
            <Card style={{ textAlign: 'center', padding: 30 }} className="ap-vocab-card">
              <AppIcon icon={Zap} size={40} style={{ color: 'var(--workspace-accent)' }} />
              <Statistic title="本轮正确率" value={quizRight} suffix={`/ ${quiz.length}`} style={{ margin: '12px 0' }} />
              <Space>
                <Button type="primary" onClick={loadQuiz}>
                  再来一轮
                </Button>
                <Button onClick={() => setTab('study')}>回去学习</Button>
              </Space>
            </Card>
          ) : (
            <Card key={quizIdx} className="ap-vocab-card anim-card-swap">
              <div className="ap-num" style={{ color: 'var(--workspace-subtle)', fontSize: 12.5, marginBottom: 8 }}>
                {quizIdx + 1} / {quiz.length} · 已对 {quizRight}
              </div>
              <div style={{ fontSize: 30, fontWeight: 700, textAlign: 'center', margin: '14px 0 22px' }}>
                {quiz[quizIdx].front}
                {isW && <PartOfSpeech value={quiz[quizIdx].part_of_speech} />}
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', alignItems: 'center', fontWeight: 400 }}>
                  {isW && <AmericanPhonetic value={quiz[quizIdx].phonetic} />}
                  <AccentButtons word={quiz[quizIdx].front || ''} />
                </div>
              </div>
              <div className="practice-options">
                {quiz[quizIdx].options.map((opt: string, i: number) => {
                  const isPicked = quizPicked === opt
                  const correct = opt === quiz[quizIdx].answer
                  const classes = ['ap-vocab-opt']
                  if (!quizPicked) {
                    classes.push('is-idle')
                  } else if (correct) {
                    classes.push('is-correct')
                    if (isPicked) classes.push('anim-option-pop')
                  } else if (isPicked) {
                    classes.push('is-wrong', 'anim-wrong-shake')
                  } else {
                    classes.push('is-dimmed')
                  }
                  return (
                    <button
                      key={opt}
                      type="button"
                      className={classes.join(' ')}
                      disabled={!!quizPicked}
                      onClick={() => {
                        setQuizPicked(opt)
                        if (opt === quiz[quizIdx].answer) setQuizRight(r => r + 1)
                      }}
                    >
                      <span className="ap-vocab-opt-main">
                        <span className="ap-vocab-keycap">{i + 1}</span>
                        <span className="ap-vocab-opt-label">{opt}</span>
                      </span>
                      {quizPicked && correct && (
                        <span
                          className="ap-vocab-opt-status anim-check-spring"
                          style={{ color: 'var(--workspace-success)' }}
                        >
                          <AppIcon icon={Check} size={17} strokeWidth={2.4} />
                        </span>
                      )}
                      {quizPicked && isPicked && !correct && (
                        <span className="ap-vocab-opt-status" style={{ color: 'var(--workspace-error)' }}>
                          <AppIcon icon={X} size={17} strokeWidth={2.4} />
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
              {quizPicked && (
                <div style={{ marginTop: 18, textAlign: 'center' }}>
                  <div style={{ color: 'var(--workspace-muted)', fontSize: 13.5, marginBottom: 12, whiteSpace: 'pre-wrap' }}>
                    {quiz[quizIdx].full_translation}
                  </div>
                  <Button
                    type="primary"
                    onClick={() => {
                      setQuizIdx(i => i + 1)
                      setQuizPicked(null)
                    }}
                  >
                    下一题
                  </Button>
                </div>
              )}
            </Card>
          )}
        </div>
      )}

      {tab === 'browse' && (
        <div className="ap-card panel anim-card-swap">
          <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
            <Input
              allowClear
              prefix={<AppIcon icon={Search} size={14} style={{ color: 'var(--workspace-subtle)' }} />}
              placeholder={`搜索${isW ? '单词' : '短语'}/释义`}
              style={{ width: 240 }}
              value={search}
              onChange={e => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
            <Segmented
              options={[
                { label: '全部', value: 'all' },
                { label: '新词', value: 'new' },
                { label: '学习中', value: 'learning' },
                { label: '已掌握', value: 'mastered' },
              ]}
              value={statusFilter}
              onChange={v => {
                setStatusFilter(v as string)
                setPage(1)
              }}
            />
            <span className="ap-num" style={{ color: 'var(--workspace-subtle)', fontSize: 13 }}>
              共 {browseData?.total ?? 0} 张卡片
            </span>
          </div>

          {(browseData?.items || []).map((c: StudyCard) => (
            <div
              key={c.card_id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '11px 8px',
                borderBottom: '1px solid var(--workspace-line)',
                flexWrap: 'wrap',
              }}
            >
              <span style={{ minWidth: 160, fontWeight: 600 }}>
                {c.headword || c.text}
                {isW && <PartOfSpeech value={c.part_of_speech} />}
                {isW && <AmericanPhonetic value={c.phonetic_us} />}
              </span>
              <AccentButtons word={c.headword || c.text || ''} />
              <span style={{ flex: 1, minWidth: 180, color: 'var(--workspace-muted)', fontSize: 13.5 }}>
                {c.translation?.split('\n')[0]}
              </span>
              {c.in_mistake_book && <Tag color="volcano">错题</Tag>}
              <Tag color={c.status === 'new' ? 'blue' : c.status === 'learning' ? 'orange' : 'green'}>
                {c.status === 'new' ? '新词' : c.status === 'learning' ? '学习中' : '复习中'}
              </Tag>
              <Tooltip title="收藏">
                <Button
                  type="text"
                  size="small"
                  aria-label={c.starred ? '取消收藏' : '收藏'}
                  icon={
                    <AppIcon
                      icon={Star}
                      size={15}
                      fill={c.starred ? 'currentColor' : 'none'}
                      style={c.starred ? { color: 'var(--workspace-warning)' } : undefined}
                    />
                  }
                  onClick={() => toggleStar(c.card_id)}
                />
              </Tooltip>
            </div>
          ))}

          {browseData?.items?.length === 0 && <Empty description="暂无数据" style={{ margin: '40px 0' }} />}
          <div style={{ marginTop: 14, textAlign: 'right' }}>
            <Radio.Group
              value={page}
              size="small"
              onChange={e => setPage(e.target.value)}
              options={Array.from({ length: Math.min(20, Math.ceil((browseData?.total || 0) / 30)) }, (_, i) => ({
                label: String(i + 1),
                value: i + 1,
              }))}
              optionType="button"
            />
          </div>
        </div>
      )}

      <Modal
        title={`添加自定义${isW ? '单词' : '短语'}`}
        open={customOpen}
        onCancel={() => setCustomOpen(false)}
        onOk={addCustom}
        okText="添加"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Input
            placeholder={isW ? '单词，如 ethos' : '短语，如 shed light on'}
            value={customForm.headword}
            onChange={e => setCustomForm({ ...customForm, headword: e.target.value })}
          />
          <Input.TextArea
            placeholder={isW ? '中文释义，可注明词性，如 n. 名词释义；v. 动词释义' : '中文释义'}
            rows={3}
            value={customForm.translation}
            onChange={e => setCustomForm({ ...customForm, translation: e.target.value })}
          />
          <Alert type="info" message="添加后进入「我的收藏」词书，可正常学习与复习。" />
        </Space>
      </Modal>
    </div>
  )
}
