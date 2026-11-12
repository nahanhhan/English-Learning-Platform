import {
  CalendarOutlined, ClockCircleOutlined, EditOutlined, FontSizeOutlined, LinkOutlined,
  MessageOutlined, RightOutlined, TranslationOutlined,
} from '@ant-design/icons'
import { Suspense, lazy, useEffect, useState, type ComponentProps } from 'react'
import { Link } from 'react-router-dom'
import { get, type BookProgress } from '../api'
import type { Appearance } from '../appearance'

const TrendChart = lazy(() => import('../components/TrendChart'))

const Q_TYPE_LABEL: Record<string, string> = {
  translation: '翻译', writing: '写作', small_writing: '应用文', big_writing: '图表作文',
}
const BOOK_NAME: Record<string, string> = {
  cet6: '六级核心词', kaoyan: '考研核心词', exam: '考试短语', custom: '我的收藏',
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

export default function Dashboard({ appearance }: { appearance: Appearance }) {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    get<Overview>('/api/stats/dashboard')
      .then(result => { if (active) setData(result) })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [attempt])

  const dueTotal = data ? data.due.words + data.due.phrases : undefined
  const metrics = [
    { label: '连续打卡', value: data?.streak, unit: '天' },
    { label: '今日复习', value: data?.today.reviews, unit: '次' },
    { label: '今日练习', value: data?.today.practices, unit: '篇' },
    { label: '待复习', value: dueTotal, unit: '项' },
  ]
  const practiceLinks = [
    { path: '/vocab', label: '复习单词', Icon: FontSizeOutlined, count: data?.due.words },
    { path: '/phrases', label: '复习短语', Icon: LinkOutlined, count: data?.due.phrases },
    { path: '/practice/translation', label: '练真题翻译', Icon: TranslationOutlined },
    { path: '/short-translation', label: '练短句翻译', Icon: MessageOutlined },
    { path: '/practice/writing', label: '写一篇作文', Icon: EditOutlined },
  ]

  return (
    <div className="page dashboard-page">
      <header className="page-heading dashboard-heading">
        <h1 className="page-title">学习概览</h1>
        <time className="dashboard-date">
          <CalendarOutlined aria-hidden="true" />
          {new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date())}
        </time>
      </header>
      <section className="dashboard-summary" aria-label="学习统计" aria-busy={!data && !error}>
        {metrics.map(({ label, value, unit }) => (
          <div className="dashboard-metric" key={label}>
            <span>{label}</span>
            <div><strong className="dashboard-value">{value ?? '—'}</strong>{value !== undefined && <small>{unit}</small>}</div>
          </div>
        ))}
      </section>
      {error && (
        <div className="panel dashboard-error" role="alert">
          <div><strong>学习统计加载失败</strong><p>{error}</p></div>
          <button type="button" className="workspace-menu-button" onClick={() => {
            setError('')
            setAttempt(current => current + 1)
          }}>重试</button>
        </div>
      )}
      <div className="dashboard-details">
        <section className="dashboard-trend dashboard-section" aria-labelledby="dashboard-trend-title">
          <header className="dashboard-section-heading">
            <h2 id="dashboard-trend-title">成绩趋势</h2>
            {data && data.trend.length > 0 && <span>{data.trend.length} 次批改</span>}
          </header>
          {!data ? <p className="dashboard-placeholder" role="status">{error ? '暂时无法读取成绩' : '正在读取成绩…'}</p>
            : data.trend.length ? <Suspense fallback={<p className="dashboard-placeholder" role="status">正在绘制趋势…</p>}>
              <TrendChart trend={data.trend} appearance={appearance} />
            </Suspense> : <p className="dashboard-placeholder">完成第一次批改后显示成绩趋势</p>}
        </section>
        <aside className="dashboard-sidebar" aria-label="词书进度和练习入口">
          <section className="dashboard-books dashboard-section" aria-labelledby="dashboard-books-title">
            <header className="dashboard-section-heading"><h2 id="dashboard-books-title">词书进度</h2></header>
            {!data ? <p className="dashboard-placeholder" role="status">{error ? '暂时无法读取进度' : '正在读取进度…'}</p>
              : [...data.word_books, ...data.phrase_books].map((book, index) => (
                <div className="dashboard-book" key={`${index < data.word_books.length ? 'word' : 'phrase'}:${book.book}`}>
                  <div><strong>{BOOK_NAME[book.book] || book.book}</strong><span>{book.started} / {book.total_items}</span></div>
                  <progress value={book.started} max={book.total_items || 1} aria-label={`${BOOK_NAME[book.book] || book.book}学习进度`} />
                  <small>已掌握 {book.mastered} · 待复习 {book.due_now}</small>
                </div>
              ))}
          </section>
          <nav className="dashboard-actions dashboard-section" aria-labelledby="dashboard-actions-title">
            <header className="dashboard-section-heading"><h2 id="dashboard-actions-title">开始练习</h2></header>
            {practiceLinks.map(({ path, label, Icon, count }) => (
              <Link to={path} key={path}>
                <Icon className="dashboard-action-icon" aria-hidden="true" />
                <span>{label}</span>
                {count !== undefined && <span className="dashboard-action-count" aria-label={`${count} 项待复习`}>{count}</span>}
                <RightOutlined className="dashboard-action-arrow" aria-hidden="true" />
              </Link>
            ))}
          </nav>
        </aside>
        <section className="dashboard-recent dashboard-section" aria-labelledby="dashboard-recent-title">
          <header className="dashboard-section-heading"><h2 id="dashboard-recent-title">最近练习</h2></header>
          {!data ? <p role="status">{error ? '暂时无法读取记录' : '正在读取记录…'}</p> : data.recent.length === 0 ? (
            <p className="dashboard-placeholder">还没有练习记录</p>
          ) : (
            <div className="dashboard-table-scroll">
              <table className="dashboard-table" aria-labelledby="dashboard-recent-title">
                <thead><tr><th scope="col">题目</th><th scope="col">类型</th><th scope="col">得分</th><th scope="col">时间</th></tr></thead>
                <tbody>{data.recent.map(row => (
                  <tr key={row.id}>
                    <td><div className="dashboard-record-title">
                      {row.q_type === 'translation' ? <TranslationOutlined aria-hidden="true" /> : <EditOutlined aria-hidden="true" />}
                      <span>{row.title || '自由练习'}</span>
                    </div></td>
                    <td>{Q_TYPE_LABEL[row.q_type] || row.q_type}</td>
                    <td>{row.score != null
                      ? <span className="dashboard-score">{row.score}<span> / {row.full_score}</span></span>
                      : <span className={row.status === 'failed' ? 'dashboard-failed' : 'dashboard-pending'}>
                        {row.status !== 'failed' && <ClockCircleOutlined aria-hidden="true" />}
                        {row.status === 'failed' ? '失败' : '批改中'}
                      </span>}</td>
                    <td><time dateTime={row.created_at.replace(' ', 'T')}>{row.created_at.slice(5, 16)}</time></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
