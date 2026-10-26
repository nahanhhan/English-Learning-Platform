import {
  CheckCircleFilled, CloseCircleFilled,
  PlusOutlined, SearchOutlined, SoundOutlined, StarFilled, StarOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Alert, Badge, Button, Card, Empty, Input, type InputRef, Modal, Progress, Radio, Segmented,
  Select, Space, Statistic, Tag, Tooltip, message,
} from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { get, post, type BookProgress, type StudyCard } from '../api'
import { cancelPendingSpeech, speak, stopSpeaking } from '../speak'
import VolumeControl from '../components/VolumeControl'
import AmericanPhonetic from '../components/AmericanPhonetic'
import PartOfSpeech from '../components/PartOfSpeech'

function AccentButtons({ word }: { word: string }) {
  return (
    <span style={{ display: 'inline-flex', gap: 6, marginLeft: 10, verticalAlign: 'middle' }}>
      <Button size="small" icon={<SoundOutlined />} onClick={(e) => { e.stopPropagation(); speak(word, 'uk') }}>英</Button>
      <Button size="small" icon={<SoundOutlined />} onClick={(e) => { e.stopPropagation(); speak(word, 'us') }}>美</Button>
    </span>
  )
}

type Tab = 'study' | 'mistake' | 'quiz' | 'browse'
type Stage = 'choice' | 'spell' | 'done'
type Source = 'normal' | 'mistake'

const RATING_LABEL: Record<string, { text: string; color: string }> = {
  good: { text: '回答正确 · 认识', color: '#52c41a' },
  hard: { text: '拼写有误 · 模糊', color: '#e6a23c' },
  again: { text: '回答错误 · 不认识', color: '#f5222d' },
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
  const [autoSpeak, setAutoSpeak] = useState(false)   // 设置未读到之前按关闭处理
  const queueSeqRef = useRef(0)        // 队列请求序号：用于丢弃过期响应
  const queueLoadingRef = useRef(false)
  const queueGenRef = useRef(0)        // 队列代次：每采用一个新队列加一
  const spokenKeyRef = useRef('')      // 最后一次已自动发音的「代次:下标」

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
  const nameOf = (b: string) => (b === 'cet6' ? '六级核心词' : b === 'kaoyan' ? '考研核心词' : b === 'exam' ? '考试短语' : '我的收藏')

  const loadBooks = useCallback(async () => {
    const data = await get<BookProgress[]>(isW ? '/api/vocab/books?item_type=word' : '/api/phrases/books')
    setBooks(data)
    setBook((b) => (b && data.find((d) => d.book === b) ? b : data[0]?.book || ''))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isW])

  useEffect(() => { loadBooks().catch((e) => message.error(e.message)) }, [loadBooks])

  const loadMistakes = useCallback(async () => {
    const url = isW ? `/api/vocab/mistakes?book=${book}&item_type=word` : `/api/phrases/mistakes?book=${book}`
    setMistakes(await get(url))
  }, [book, isW])

  useEffect(() => {
    if (book) loadMistakes().catch(() => {})
  }, [book, loadMistakes])

  const loadQueue = useCallback(async (src: Source = source) => {
    if (!book) return
    stopSpeaking()
    const seq = ++queueSeqRef.current
    queueLoadingRef.current = true
    resetCardState()
    setQueueIdx(0)
    const base = isW ? `/api/vocab/queue?book=${book}&item_type=word` : `/api/phrases/queue?book=${book}`
    try {
      const data = await get(`${base}&source=${src}`)
      if (seq !== queueSeqRef.current) return   // 已有更新的请求在跑，丢弃这个过期响应
      queueLoadingRef.current = false
      queueGenRef.current += 1
      setQueue(data)
    } catch (e) {
      if (seq === queueSeqRef.current) queueLoadingRef.current = false
      throw e
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [book, isW, source])

  useEffect(() => {
    if (tab === 'study') loadQueue().catch((e) => message.error(e.message))
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
    if (advanceRef.current) { clearTimeout(advanceRef.current); advanceRef.current = null }
  }

  const cards = useMemo(() => {
    if (!queue) return []
    return [...queue.review, ...queue.new]
  }, [queue])
  const currentCard = cards[queueIdx]

  // 读取「自动发音」偏好：读不到就按关闭处理，避免关掉开关后仍出声
  useEffect(() => {
    let alive = true
    get('/api/settings')
      .then((d) => { if (alive) setAutoSpeak(d?.prefs?.auto_speak !== '0') })
      .catch(() => { /* 读不到保持关闭 */ })
    return () => { alive = false }
  }, [])

  // 先取消旧题，再启动新题；阶段变化只取消未开始的声音，避免截断同一单词。
  useEffect(() => { stopSpeaking() }, [book, tab, currentCard?.card_id, quizIdx, page, search, statusFilter, customOpen])
  useEffect(() => { cancelPendingSpeech() }, [stage])

  // 换到新卡片时自动朗读美音：同一代次、同一下标只读一次
  useEffect(() => {
    if (tab !== 'study' || stage !== 'choice') return
    if (!autoSpeak || queueLoadingRef.current || !currentCard) return
    const key = `${queueGenRef.current}:${queueIdx}`
    if (spokenKeyRef.current === key) return
    spokenKeyRef.current = key
    speak(currentCard.headword || currentCard.text || '', 'us')
  }, [tab, stage, currentCard, queueIdx, autoSpeak])

  // 切离学习 Tab 或离开页面时，停掉正在播放的自动发音
  useEffect(() => {
    if (tab !== 'study') stopSpeaking()
  }, [tab])

  useEffect(() => () => stopSpeaking(), [])

  const nextCard = useCallback(async () => {
    if (advanceRef.current) { clearTimeout(advanceRef.current); advanceRef.current = null }
    if (queueIdx + 1 >= cards.length) {
      // 本轮结束：again 的卡因到期会重新入队
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
      setQueueIdx((i) => i + 1)
      resetCardState()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queueIdx, cards.length, book, isW, source, loadBooks, loadMistakes])

  const finishCard = useCallback(async (rating: 'good' | 'hard' | 'again') => {
    if (!currentCard) return
    try {
      const resp = await post<StudyCard>(isW ? '/api/vocab/answer' : '/api/phrases/answer', {
        card_id: currentCard.card_id, rating,
      })
      setSessionDone((s) => s + 1)
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
  }, [currentCard, isW, nextCard, loadMistakes])

  // ---------- 选择题 ----------
  const pick = (opt: string) => {
    if (!currentCard || locked || stage !== 'choice') return
    setLocked(true)
    setPicked(opt)
    const right = opt === currentCard.answer
    setChoiceRight(right)
    setTimeout(() => {
      if (isW) {
        setStage('spell')   // 单词：进入拼写
      } else {
        finishCard(right ? 'good' : 'again')  // 短语：直接结算
      }
    }, 950)
  }

  // ---------- 拼写 ----------
  const spellHint = useMemo(() => {
    const w = currentCard?.headword || ''
    return w.split('').map((ch, i) => (i === 0 || !/[a-zA-Z]/.test(ch)) ? ch : '_').join(' ')
  }, [currentCard])

  const submitSpell = () => {
    const target = (currentCard?.headword || '').trim()
    const ok = spellInput.trim().toLowerCase() === target.toLowerCase()
    if (!ok) {
      setSpellWrong(true)   // 展示正确拼写，重打一次
      setSpellInput('')
      spellInputRef.current?.focus({ preventScroll: true })
      return
    }
    if (!choiceRight) finishCard('again')          // 选择已错：仅补拼写强化
    else if (spellWrong) finishCard('hard')        // 拼写首试错
    else finishCard('good')                        // 全对
  }

  // 键盘：1-4 选择；Enter 提交拼写 / 下一张
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
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

  // ---------- 测验 ----------
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

  // ---------- 词表 ----------
  const loadBrowse = useCallback(async () => {
    if (!book) return
    const params = new URLSearchParams({ book, page: String(page), page_size: '30', status: statusFilter })
    if (search.trim()) params.set('search', search.trim())
    const url = isW ? `/api/vocab/browse?item_type=word&${params}` : `/api/phrases/browse?${params}`
    setBrowseData(await get(url))
  }, [book, page, statusFilter, search, isW])

  useEffect(() => {
    if (tab === 'browse') loadBrowse().catch((e) => message.error(e.message))
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

  const bookInfo = books.find((b) => b.book === book)
  const totalQueue = queue ? queue.counts.review + queue.counts.new : 0
  const queueLabel = source === 'mistake' ? '错题专项练习' : '今日学习'

  // ---------- 学习 Tab 渲染 ----------
  const renderStudy = () => {
    if (!queue || (!totalQueue && !cards.length)) {
      return <Empty description={source === 'mistake' ? '错题本已清空 🎉' : '今日队列已清空，休息一下 ☕'} style={{ marginTop: 60 }} />
    }
    if (!currentCard) return <Empty description="加载中…" style={{ marginTop: 60 }} />

    return (
      <>
        <div className="study-question-meta">
          <Space size={8}>
            {source === 'mistake' ? <Tag color="red">错题专项</Tag> : <Tag color="blue">今日队列</Tag>}
            {currentCard.status === 'new' ? <Tag color="geekblue">新词</Tag> : <Tag color="orange">复习</Tag>}
            {currentCard.in_mistake_book && <Tag color="volcano">错题连对 {currentCard.mistake_consec}/3</Tag>}
          </Space>
          <span style={{ color: '#bbb', fontSize: 12.5 }}>{queueIdx + 1} / {cards.length} · 本轮完成 {sessionDone}</span>
        </div>
        <Progress percent={Math.round((queueIdx / Math.max(cards.length, 1)) * 100)} size={['100%', 5]} showInfo={false} className="study-progress" />

        {stage === 'choice' && (
          <Card className="study-practice-card">
            <div className="study-prompt">
              <div className="study-headword">
                {currentCard.headword || currentCard.text}
                {isW && <PartOfSpeech value={currentCard.part_of_speech} />}
              </div>
              {isW && <AmericanPhonetic value={currentCard.phonetic_us} />}
              <div style={{ marginTop: 8, fontSize: 14, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 4 }}>
                <AccentButtons word={currentCard.headword || currentCard.text || ''} />
              </div>
              <div style={{ color: '#bbb', fontSize: 12.5, marginTop: 10 }}>选择正确的{isW ? '中文释义' : '释义'}（快捷键 1-4）</div>
            </div>
            <div className="practice-options">
              {(currentCard.options || []).map((opt, i) => {
                const isPicked = picked === opt
                const isAnswer = opt === currentCard.answer
                let bg = '#fff', bd = '#d9dce1'
                if (picked) {
                  if (isAnswer) { bg = '#f6ffed'; bd = '#b7eb8f' }       // 正确答案：绿
                  else if (isPicked) { bg = '#fff1f0'; bd = '#ffa39e' }   // 选错：红
                  else bg = '#fafafa'
                }
                return (
                  <Button
                    key={opt + i} block size="large" disabled={!!picked} className="study-option"
                    style={{ background: bg, borderColor: bd }}
                    onClick={() => pick(opt)}
                  >
                    <span style={{ color: '#999', marginRight: 10, fontSize: 12 }}>{i + 1}</span>
                    {opt}
                    {picked && isAnswer && <CheckCircleFilled style={{ color: '#52c41a', float: 'right', marginTop: 4 }} />}
                    {picked && isPicked && !isAnswer && <CloseCircleFilled style={{ color: '#f5222d', float: 'right', marginTop: 4 }} />}
                  </Button>
                )
              })}
            </div>
          </Card>
        )}

        {stage === 'spell' && (
          <Card className="study-practice-card">
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {currentCard.answer}
              </div>
              <div style={{ marginTop: 6, display: 'flex', justifyContent: 'center' }}>
                <AccentButtons word={currentCard.headword || ''} />
              </div>
              <div style={{ color: '#999', fontSize: 13, marginTop: 6 }}>
                {choiceRight ? '拼写这个单词' : '选择有误，拼写一下加深记忆'}
              </div>
              <div style={{ marginTop: 10, fontSize: 18, letterSpacing: 4, color: '#3562a7', fontFamily: 'monospace' }}>
                {spellWrong ? currentCard.headword : spellHint}
                <PartOfSpeech value={currentCard.part_of_speech} />
              </div>
            </div>
            <Space.Compact style={{ width: '100%', maxWidth: 420, display: 'flex', margin: '0 auto' }}>
              <Input
                ref={spellInputRef}
                size="large" placeholder={spellWrong ? `正确拼写：${currentCard.headword}（重打一遍）` : '输入拼写后回车'}
                value={spellInput} autoFocus
                onChange={(e) => setSpellInput(e.target.value)}
                onPressEnter={submitSpell}
                status={spellWrong ? 'error' : undefined}
              />
              <Button size="large" type="primary" onClick={submitSpell}>提交</Button>
            </Space.Compact>
            {spellWrong && (
              <div style={{ textAlign: 'center', marginTop: 12 }}>
                <Tag color="red">拼写错误</Tag>
                <span style={{ fontSize: 13.5 }}>请按提示重打一遍正确拼写，本词已计入错题本</span>
              </div>
            )}
          </Card>
        )}

        {stage === 'done' && cardResult && (() => {
          const rating = choiceRight ? (spellWrong ? 'hard' : 'good') : 'again'
          const meta = RATING_LABEL[rating]
          const enteredBook = cardResult.in_mistake_book && !currentCard.in_mistake_book
          const removedBook = !cardResult.in_mistake_book && currentCard.in_mistake_book
          return (
            <Card className="study-practice-card" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 42, marginBottom: 8 }}>
                {rating === 'good' ? '🎉' : rating === 'hard' ? '😅' : '💪'}
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: meta.color, marginBottom: 6 }}>{meta.text}</div>
              <div style={{ color: '#666', fontSize: 14 }}>
                <b>{currentCard.headword || currentCard.text}</b>
                {isW && <PartOfSpeech value={currentCard.part_of_speech} />}
                <span style={{ margin: '0 8px', color: '#ddd' }}>|</span>
                {currentCard.answer}
              </div>
              <div style={{ marginTop: 10 }}>
                {removedBook && <Tag color="green">连对 3 次，已移出错题本 🎉</Tag>}
                {enteredBook && <Tag color="volcano">已加入错题本</Tag>}
                {!enteredBook && !removedBook && cardResult.in_mistake_book &&
                  <Tag color="orange">错题连对 {cardResult.mistake_consec}/3</Tag>}
              </div>
              {rating !== 'good' && (
                <Button type="primary" style={{ marginTop: 18 }} onClick={nextCard}>下一张（Enter）</Button>
              )}
            </Card>
          )
        })()}

        <div style={{ textAlign: 'center', color: '#bbb', fontSize: 12.5, marginTop: 12 }}>
          {isW ? '快捷键：1-4 选择 · Enter 提交拼写/下一张' : '快捷键：1-4 选择 · 答对自动进入下一张'}
        </div>
      </>
    )
  }

  return (
    <div className="page study-page">
      <div className="study-toolbar">
        <div>
          <h1 className="page-title">{isW ? '背单词' : '背短语'}</h1>
          <div className="page-subtitle">
            四选一选择{isW ? ' + 拼写强化' : ''} · 答错自动进入错题本，连对 3 次移出
          </div>
        </div>
        <Space wrap>
          <VolumeControl />
          <Select
            style={{ minWidth: 160 }} value={book}
            options={books.map((b) => ({ label: nameOf(b.book), value: b.book }))}
            onChange={setBook}
          />
          <Button icon={<PlusOutlined />} onClick={() => setCustomOpen(true)}>添加{isW ? '单词' : '短语'}</Button>
        </Space>
      </div>

      {/* 进度概览 */}
      <div className="study-stats">
        <div className="panel">
          <Statistic title="词库总量" value={bookInfo?.total_items ?? 0} valueStyle={{ fontSize: 22 }} />
        </div>
        <div className="panel">
          <Statistic title="已开始学习" value={bookInfo?.started ?? 0} valueStyle={{ fontSize: 22, color: '#3562a7' }} />
        </div>
        <div className="panel">
          <Statistic title="已掌握" value={bookInfo?.mastered ?? 0} valueStyle={{ fontSize: 22, color: '#52c41a' }} />
        </div>
        <div className="panel">
          <Statistic title="错题本" value={mistakes.length} valueStyle={{ fontSize: 22, color: mistakes.length ? '#f5222d' : undefined }} />
        </div>
      </div>

      <Segmented
        style={{ marginBottom: 10 }}
        options={[
          { label: <span>学习{totalQueue > 0 && source === 'normal' && <Badge count={totalQueue} size="small" style={{ marginLeft: 6 }} />}</span>, value: 'study' },
          { label: <span>错题本{mistakes.length > 0 && <Badge count={mistakes.length} size="small" color="#f5222d" style={{ marginLeft: 6 }} />}</span>, value: 'mistake' },
          { label: '测验', value: 'quiz' },
          { label: '词表', value: 'browse' },
        ]}
        value={tab}
        onChange={(v) => {
          const t = v as Tab
          setTab(t)
          if (t === 'mistake') loadMistakes().catch(() => {})
        }}
      />

      {/* 学习 */}
      {tab === 'study' && (
        <div className="study-practice">
          {source === 'mistake' && (
            <div style={{ textAlign: 'center', marginBottom: 10 }}>
              <Button size="small" onClick={async () => { setSource('normal'); await loadQueue('normal') }}>
                退出专项练习，回到今日队列
              </Button>
            </div>
          )}
          {renderStudy()}
        </div>
      )}

      {/* 错题本 */}
      {tab === 'mistake' && (
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          <Card size="small" style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <span style={{ color: '#777', fontSize: 13.5 }}>
                答错即进入错题本；连对 <b>3</b> 次（单词需选择与拼写都正确）自动移出。
              </span>
              <Button type="primary" danger disabled={mistakes.length === 0}
                icon={<ThunderboltOutlined />}
                onClick={async () => { setSource('mistake'); setTab('study'); await loadQueue('mistake') }}>
                开始专项练习{mistakes.length ? `（${mistakes.length} 题）` : ''}
              </Button>
            </div>
          </Card>
          <Card size="small">
            {mistakes.length === 0 ? (
              <Empty description="错题本已清空 🎉" style={{ margin: '24px 0' }} />
            ) : mistakes.map((m) => (
              <div key={m.card_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 4px', borderBottom: '1px solid #f4f5f7' }}>
                <span style={{ minWidth: 140, fontWeight: 600 }}>{m.headword || m.text}
                  {isW && <PartOfSpeech value={m.part_of_speech} />}
                </span>
                <span style={{ flex: 1, color: '#666', fontSize: 13.5 }}>{m.translation?.split('\n')[0]}</span>
                <span style={{ fontSize: 12.5 }}>
                  {[0, 1, 2].map((i) => (
                    <span key={i} style={{
                      display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
                      marginRight: 4, background: (m.mistake_consec || 0) > i ? '#52c41a' : '#e8e8e8',
                    }} />
                  ))}
                  <span style={{ color: '#999', marginLeft: 6 }}>连对 {m.mistake_consec}/3</span>
                </span>
              </div>
            ))}
          </Card>
        </div>
      )}

      {/* 测验 */}
      {tab === 'quiz' && (
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          {quizLoading ? <Empty description="出题中…" /> : quiz.length === 0 ? (
            <Empty description="先去学习几个词再来测验吧" style={{ marginTop: 60 }} />
          ) : quizIdx >= quiz.length ? (
            <Card style={{ textAlign: 'center', padding: 30 }}>
              <ThunderboltOutlined style={{ fontSize: 40, color: '#3562a7' }} />
              <Statistic title="本轮正确率" value={quizRight} suffix={`/ ${quiz.length}`} style={{ margin: '12px 0' }} />
              <Space>
                <Button type="primary" onClick={loadQuiz}>再来一轮</Button>
                <Button onClick={() => setTab('study')}>回去学习</Button>
              </Space>
            </Card>
          ) : (
            <Card>
              <div style={{ color: '#999', fontSize: 12.5, marginBottom: 8 }}>
                {quizIdx + 1} / {quiz.length} · 已对 {quizRight}
              </div>
              <div style={{ fontSize: 28, fontWeight: 700, textAlign: 'center', margin: '18px 0 24px' }}>
                {quiz[quizIdx].front}
                {isW && <PartOfSpeech value={quiz[quizIdx].part_of_speech} />}
                <div style={{ marginTop: 6, display: 'flex', justifyContent: 'center', fontWeight: 400 }}>
                  {isW && <AmericanPhonetic value={quiz[quizIdx].phonetic} />}
                  <AccentButtons word={quiz[quizIdx].front || ''} />
                </div>
              </div>
              <Space direction="vertical" style={{ width: '100%' }} size={10}>
                {quiz[quizIdx].options.map((opt: string) => {
                  const picked = quizPicked === opt
                  const correct = opt === quiz[quizIdx].answer
                  let bg = '#fff'
                  if (quizPicked && correct) bg = '#f6ffed'
                  else if (picked && !correct) bg = '#fff1f0'
                  return (
                    <Button
                      key={opt} block size="large"
                      style={{ textAlign: 'left', background: bg, height: 'auto', padding: '10px 16px', whiteSpace: 'normal' }}
                      disabled={!!quizPicked}
                      onClick={() => {
                        setQuizPicked(opt)
                        if (opt === quiz[quizIdx].answer) setQuizRight((r) => r + 1)
                      }}
                    >
                      {opt}
                    </Button>
                  )
                })}
              </Space>
              {quizPicked && (
                <div style={{ marginTop: 16, textAlign: 'center' }}>
                  <div style={{ color: '#666', fontSize: 13, marginBottom: 10, whiteSpace: 'pre-wrap' }}>
                    {quiz[quizIdx].full_translation}
                  </div>
                  <Button type="primary" onClick={() => { setQuizIdx((i) => i + 1); setQuizPicked(null) }}>
                    下一题
                  </Button>
                </div>
              )}
            </Card>
          )}
        </div>
      )}

      {/* 词表 */}
      {tab === 'browse' && (
        <div className="panel">
          <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
            <Input
              allowClear prefix={<SearchOutlined />} placeholder={`搜索${isW ? '单词' : '短语'}/释义`}
              style={{ width: 240 }} value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            />
            <Segmented
              options={[
                { label: '全部', value: 'all' }, { label: '新词', value: 'new' },
                { label: '学习中', value: 'learning' }, { label: '已掌握', value: 'mastered' },
              ]}
              value={statusFilter}
              onChange={(v) => { setStatusFilter(v as string); setPage(1) }}
            />
            <span style={{ color: '#bbb', fontSize: 13, lineHeight: '32px' }}>共 {browseData?.total ?? 0} 张卡片</span>
          </div>
          {(browseData?.items || []).map((c: StudyCard) => (
            <div
              key={c.card_id}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '10px 8px',
                borderBottom: '1px solid #f4f5f7',
              }}
            >
              <span style={{ minWidth: 150, fontWeight: 600 }}>{c.headword || c.text}
                {isW && <PartOfSpeech value={c.part_of_speech} />}
                {isW && <AmericanPhonetic value={c.phonetic_us} />}
              </span>
              <AccentButtons word={c.headword || c.text || ''} />
              <span style={{ flex: 1, color: '#555', fontSize: 13.5 }}>{c.translation?.split('\n')[0]}</span>
              {c.in_mistake_book && <Tag color="volcano">错题</Tag>}
              <Tag color={c.status === 'new' ? 'blue' : c.status === 'learning' ? 'orange' : 'green'}>
                {c.status === 'new' ? '新词' : c.status === 'learning' ? '学习中' : '复习中'}
              </Tag>
              <Tooltip title="收藏">
                <Button
                  type="text" size="small"
                  icon={c.starred ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
                  onClick={() => toggleStar(c.card_id)}
                />
              </Tooltip>
            </div>
          ))}
          {browseData?.items?.length === 0 && <Empty description="暂无数据" style={{ margin: '40px 0' }} />}
          <div style={{ marginTop: 14, textAlign: 'right' }}>
            <Radio.Group
              value={page} size="small"
              onChange={(e) => setPage(e.target.value)}
              options={Array.from({ length: Math.min(20, Math.ceil((browseData?.total || 0) / 30)) }, (_, i) => ({ label: String(i + 1), value: i + 1 }))}
              optionType="button"
            />
          </div>
        </div>
      )}

      <Modal
        title={`添加自定义${isW ? '单词' : '短语'}`} open={customOpen}
        onCancel={() => setCustomOpen(false)} onOk={addCustom} okText="添加"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Input placeholder={isW ? '单词，如 ethos' : '短语，如 shed light on'} value={customForm.headword} onChange={(e) => setCustomForm({ ...customForm, headword: e.target.value })} />
          <Input.TextArea placeholder={isW ? '中文释义，可注明词性，如 n. 名词释义；v. 动词释义' : '中文释义'} rows={3} value={customForm.translation} onChange={(e) => setCustomForm({ ...customForm, translation: e.target.value })} />
          <Alert type="info" message="添加后进入「我的收藏」词书，可正常学习与复习。" />
        </Space>
      </Modal>
    </div>
  )
}
