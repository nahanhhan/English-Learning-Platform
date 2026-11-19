import {
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Clock,
  Flame,
  Languages,
  Link2,
  MessageSquare,
  PencilLine,
} from 'lucide-react'
import { Suspense, lazy, useEffect, useState, type ComponentProps, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { get, type BookProgress } from '../api'
import type { Appearance } from '../appearance'
import AppIcon from '../components/AppIcon'

const TrendChart = lazy(() => import('../components/TrendChart'))

const Q_TYPE_LABEL: Record<string, string> = {
  translation: '翻译',
  writing: '写作',
  small_writing: '应用文',
  big_writing: '图表作文',
}

const BOOK_NAME: Record<string, string> = {
  cet6: '六级核心词',
  kaoyan: '考研核心词',
  exam: '考试短语',
  custom: '我的收藏',
}

interface RecentPractice {
  id: number
  title: string
  q_type: string
  score: number | null
  full_score: number | null
  status: string
  created_at: string
}

interface Overview {
  streak: number
  today: { reviews: number; practices: number }
  due: { words: number; phrases: number }
  trend: ComponentProps<typeof TrendChart>['trend']
  word_books: BookProgress[]
  phrase_books: BookProgress[]
  recent: RecentPractice[]
}

function scoreTone(score: number, fullScore: number) {
  const ratio = fullScore > 0 ? score / fullScore : 0
  if (ratio >= 0.85) return { bg: 'var(--workspace-success-bg)', color: 'var(--workspace-success)' }
  if (ratio >= 0.7) return { bg: 'var(--workspace-accent-bg)', color: 'var(--workspace-accent)' }
  return { bg: 'var(--workspace-warning-bg)', color: 'var(--workspace-warning)' }
}

export default function Dashboard({ appearance }: { appearance: Appearance }) {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [barsReady, setBarsReady] = useState(false)

  useEffect(() => {
    let active = true
    setBarsReady(false)
    get<Overview>('/api/stats/dashboard')
      .then(result => {
        if (!active) return
        setData(result)
        requestAnimationFrame(() => {
          if (active) setBarsReady(true)
        })
      })
      .catch(err => {
        if (active) setError(err.message)
      })
    return () => {
      active = false
    }
  }, [attempt])

  const dueTotal = data ? data.due.words + data.due.phrases : undefined
  const metrics = [
    {
      label: '连续打卡',
      value: data?.streak,
      unit: '天',
      Icon: Flame,
      bg: 'var(--workspace-warning-bg)',
      color: 'var(--workspace-warning)',
      due: false,
    },
    {
      label: '今日复习',
      value: data?.today.reviews,
      unit: '次',
      Icon: CheckCircle2,
      bg: 'var(--workspace-accent-bg)',
      color: 'var(--workspace-accent)',
      due: false,
    },
    {
      label: '今日练习',
      value: data?.today.practices,
      unit: '篇',
      Icon: PencilLine,
      bg: 'var(--workspace-success-bg)',
      color: 'var(--workspace-success)',
      due: false,
    },
    {
      label: '待复习',
      value: dueTotal,
      unit: '项',
      Icon: Clock,
      bg: 'var(--workspace-accent-bg)',
      color: 'var(--workspace-accent)',
      due: true,
    },
  ]

  const practiceLinks = [
    {
      path: '/vocab',
      label: '复习单词',
      Icon: BookOpen,
      count: data?.due.words,
      bg: 'var(--workspace-accent-bg)',
      color: 'var(--workspace-accent)',
    },
    {
      path: '/phrases',
      label: '复习短语',
      Icon: Link2,
      count: data?.due.phrases,
      bg: 'var(--workspace-success-bg)',
      color: 'var(--workspace-success)',
    },
    {
      path: '/practice/translation',
      label: '练真题翻译',
      Icon: Languages,
      bg: 'var(--workspace-warning-bg)',
      color: 'var(--workspace-warning)',
    },
    {
      path: '/short-translation',
      label: '练短句翻译',
      Icon: MessageSquare,
      bg: 'var(--workspace-accent-bg)',
      color: 'var(--workspace-indigo)',
    },
    {
      path: '/practice/writing',
      label: '写一篇作文',
      Icon: PencilLine,
      bg: 'var(--workspace-purple-bg)',
      color: 'var(--workspace-purple)',
    },
  ]

  return (
    <div className="page dashboard-page">
      <header className="page-heading dashboard-heading ap-stagger" style={{ '--stagger-i': 0 } as CSSProperties}>
        <div>
          <h1 className="page-title">学习概览</h1>
          <p className="page-subtitle">今日词汇进度、真题批改成绩与快捷练习入口</p>
        </div>
        <time className="dashboard-date">
          <AppIcon icon={Calendar} size={14} />
          {new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date())}
        </time>
      </header>

      <section className="dashboard-summary" aria-label="学习统计" aria-busy={!data && !error}>
        {metrics.map(({ label, value, unit, Icon, bg, color, due }, index) => (
          <div
            className={`ap-card ap-card-interactive ap-stagger dashboard-metric${due ? ' dashboard-metric-due' : ''}`}
            key={label}
            style={{ '--stagger-i': index + 1 } as CSSProperties}
          >
            <div>
              <span className="dashboard-metric-label">{label}</span>
              <div className="dashboard-metric-row">
                <strong className="dashboard-value">{value ?? '—'}</strong>
                {value !== undefined && <small>{unit}</small>}
              </div>
            </div>
            <span className="dashboard-metric-badge" style={{ background: bg, color }} aria-hidden="true">
              <AppIcon icon={Icon} size={16} strokeWidth={1.8} />
            </span>
          </div>
        ))}
      </section>

      {error && (
        <div className="panel dashboard-error" role="alert">
          <div>
            <strong>学习统计加载失败</strong>
            <p>{error}</p>
          </div>
          <button
            type="button"
            className="workspace-menu-button ap-press"
            onClick={() => {
              setError('')
              setAttempt(current => current + 1)
            }}
          >
            重试
          </button>
        </div>
      )}

      <div className="dashboard-details">
        <section
          className="ap-card ap-stagger dashboard-trend dashboard-section"
          style={{ '--stagger-i': 2 } as CSSProperties}
          aria-labelledby="dashboard-trend-title"
        >
          <header className="dashboard-section-heading">
            <h2 id="dashboard-trend-title">成绩趋势</h2>
            {data && data.trend.length > 0 && <span>{data.trend.length} 次批改</span>}
          </header>
          {!data ? (
            <p className="dashboard-placeholder" role="status">
              {error ? '暂时无法读取成绩' : '正在读取成绩…'}
            </p>
          ) : data.trend.length ? (
            <Suspense fallback={<p className="dashboard-placeholder" role="status">正在绘制趋势…</p>}>
              <TrendChart trend={data.trend} appearance={appearance} />
            </Suspense>
          ) : (
            <p className="dashboard-placeholder">完成第一次批改后显示成绩趋势</p>
          )}
        </section>

        <aside className="dashboard-sidebar" aria-label="词书进度和练习入口">
          <section
            className="ap-card ap-stagger dashboard-books dashboard-section"
            style={{ '--stagger-i': 3 } as CSSProperties}
            aria-labelledby="dashboard-books-title"
          >
            <header className="dashboard-section-heading">
              <h2 id="dashboard-books-title">词书进度</h2>
            </header>
            {!data ? (
              <p className="dashboard-placeholder" role="status">
                {error ? '暂时无法读取进度' : '正在读取进度…'}
              </p>
            ) : (
              [...data.word_books, ...data.phrase_books].map((book, index) => {
                const isPhrase = index >= data.word_books.length
                const total = book.total_items || 1
                const pct = Math.min(100, Math.round((book.started / total) * 100))
                const label = BOOK_NAME[book.book] || book.book
                return (
                  <div className="dashboard-book" key={`${isPhrase ? 'phrase' : 'word'}:${book.book}`}>
                    <div className="dashboard-book-head">
                      <strong>{label}</strong>
                      <span>
                        {book.started} / {book.total_items}
                      </span>
                    </div>
                    <div
                      className="dashboard-book-track"
                      role="progressbar"
                      aria-label={`${label}学习进度`}
                      aria-valuemin={0}
                      aria-valuemax={total}
                      aria-valuenow={book.started}
                    >
                      <div
                        className="dashboard-book-fill ap-progress-fill"
                        style={{
                          width: barsReady ? `${pct}%` : '0%',
                          background: isPhrase ? 'var(--workspace-success-solid)' : 'var(--workspace-accent)',
                        }}
                      />
                    </div>
                    <small>
                      已掌握 {book.mastered} · 待复习 {book.due_now}
                    </small>
                  </div>
                )
              })
            )}
          </section>

          <nav
            className="ap-card ap-stagger dashboard-actions dashboard-section"
            style={{ '--stagger-i': 4 } as CSSProperties}
            aria-labelledby="dashboard-actions-title"
          >
            <header className="dashboard-section-heading">
              <h2 id="dashboard-actions-title">开始练习</h2>
            </header>
            <div className="dashboard-actions-list">
              {practiceLinks.map(({ path, label, Icon, count, bg, color }) => (
                <Link to={path} key={path} className="ap-press">
                  <span className="dashboard-action-badge" style={{ background: bg, color }} aria-hidden="true">
                    <AppIcon icon={Icon} size={15} strokeWidth={1.75} />
                  </span>
                  <span>{label}</span>
                  {count !== undefined && (
                    <span className="dashboard-action-count" aria-label={`${count} 项待复习`}>
                      {count}
                    </span>
                  )}
                  <AppIcon icon={ChevronRight} size={14} className="dashboard-action-arrow" />
                </Link>
              ))}
            </div>
          </nav>
        </aside>

        <section
          className="ap-card ap-stagger dashboard-recent dashboard-section"
          style={{ '--stagger-i': 3 } as CSSProperties}
          aria-labelledby="dashboard-recent-title"
        >
          <header className="dashboard-section-heading">
            <h2 id="dashboard-recent-title">最近练习</h2>
            <Link to="/practice/translation" className="dashboard-more-link">
              前往真题练习 →
            </Link>
          </header>
          {!data ? (
            <p role="status">{error ? '暂时无法读取记录' : '正在读取记录…'}</p>
          ) : data.recent.length === 0 ? (
            <p className="dashboard-placeholder">还没有练习记录</p>
          ) : (
            <div className="dashboard-table-scroll">
              <table className="dashboard-table" aria-labelledby="dashboard-recent-title">
                <thead>
                  <tr>
                    <th scope="col">题目</th>
                    <th scope="col">类型</th>
                    <th scope="col">得分</th>
                    <th scope="col">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map(row => {
                    const tone =
                      row.score != null ? scoreTone(row.score, row.full_score || 15) : null
                    return (
                      <tr key={row.id}>
                        <td>
                          <div className="dashboard-record-title">
                            <AppIcon
                              icon={row.q_type === 'translation' ? Languages : PencilLine}
                              size={14}
                            />
                            <span>{row.title || '自由练习'}</span>
                          </div>
                        </td>
                        <td>{Q_TYPE_LABEL[row.q_type] || row.q_type}</td>
                        <td>
                          {row.score != null && tone ? (
                            <span
                              className="dashboard-score-pill"
                              style={{ background: tone.bg, color: tone.color }}
                            >
                              {row.score} / {row.full_score}
                            </span>
                          ) : row.status === 'failed' ? (
                            <span
                              className="dashboard-score-pill"
                              style={{
                                background: 'var(--workspace-error-bg)',
                                color: 'var(--workspace-error)',
                              }}
                            >
                              失败
                            </span>
                          ) : (
                            <span
                              className="dashboard-score-pill"
                              style={{
                                background: 'var(--workspace-warning-bg)',
                                color: 'var(--workspace-warning)',
                              }}
                            >
                              <AppIcon icon={Clock} size={12} />
                              批改中
                            </span>
                          )}
                        </td>
                        <td>
                          <time dateTime={row.created_at.replace(' ', 'T')}>
                            {row.created_at.slice(5, 16)}
                          </time>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
