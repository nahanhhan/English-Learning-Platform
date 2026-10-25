import {
  CalendarOutlined, CheckSquareOutlined, FireOutlined, ReadOutlined,
} from '@ant-design/icons'
import { Card, Col, Empty, Progress, Row, Spin, Statistic, Table, Tag } from 'antd'
import { Suspense, lazy, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../api'

const TrendChart = lazy(() => import('../components/TrendChart'))

const Q_TYPE_LABEL: Record<string, string> = {
  translation: '翻译', writing: '写作', small_writing: '应用文', big_writing: '图表作文',
}
const BOOK_NAME: Record<string, string> = {
  cet6: '六级核心词', kaoyan: '考研核心词', exam: '考试短语', custom: '我的收藏',
}

export default function Dashboard() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    get('/api/stats/dashboard').then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="page"><Card>{error}</Card></div>
  if (!data) return <div className="page" style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>

  const dueTotal = (data.due?.words || 0) + (data.due?.phrases || 0)

  return (
    <div className="page">
      <h1 className="page-title">学习概览</h1>
      <div className="page-subtitle">坚持就是胜利，今天也要加油 💪</div>

      {/* 顶部统计卡 */}
      <Row gutter={[14, 14]}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="连续打卡" value={data.streak} suffix="天" prefix={<FireOutlined style={{ color: '#fa541c' }} />} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="今日复习" value={data.today.reviews} suffix="次" prefix={<CheckSquareOutlined style={{ color: '#3562a7' }} />} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="今日练习" value={data.today.practices} suffix="篇" prefix={<CalendarOutlined style={{ color: '#52c41a' }} />} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="待复习" value={dueTotal} suffix="项" prefix={<ReadOutlined style={{ color: '#e6a23c' }} />} />
          </Card>
        </Col>
      </Row>

      {/* 快捷入口 */}
      <div style={{ margin: '14px 0', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Link to="/practice/translation"><Tag.CheckableTag checked style={{ fontSize: 13 }}>✍️ 练一篇翻译</Tag.CheckableTag></Link>
        <Link to="/practice/writing"><Tag.CheckableTag checked style={{ fontSize: 13 }}>📝 写一篇作文</Tag.CheckableTag></Link>
        <Link to="/vocab"><Tag.CheckableTag checked style={{ fontSize: 13 }}>📖 背单词（{data.due.words} 待复习）</Tag.CheckableTag></Link>
        <Link to="/phrases"><Tag.CheckableTag checked style={{ fontSize: 13 }}>🔗 背短语（{data.due.phrases} 待复习）</Tag.CheckableTag></Link>
      </div>

      <Row gutter={[14, 14]}>
        {/* 成绩趋势 */}
        <Col xs={24} lg={14}>
          <Card title="翻译 / 作文成绩趋势" size="small">
            {data.trend.length === 0
              ? <Empty description="完成第一次批改后这里会显示你的分数曲线" style={{ padding: '40px 0' }} />
              : <Suspense fallback={<div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Spin /></div>}>
                  <TrendChart trend={data.trend} />
                </Suspense>}
          </Card>
        </Col>

        {/* 词书进度 */}
        <Col xs={24} lg={10}>
          <Card title="词书进度" size="small">
            {[...data.word_books, ...data.phrase_books].map((b: any) => {
              const pct = b.total_items ? Math.round((b.started / b.total_items) * 100) : 0
              return (
                <div key={b.book} style={{ marginBottom: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>{BOOK_NAME[b.book] || b.book}</span>
                    <span style={{ color: '#888' }}>
                      已学 {b.started} / {b.total_items} · 掌握 {b.mastered} · 待复习 {b.due_now}
                    </span>
                  </div>
                  <Progress percent={pct} size={['100%', 8]} strokeColor={pct >= 80 ? '#52c41a' : '#3562a7'} />
                </div>
              )
            })}
          </Card>
        </Col>

        {/* 最近练习 */}
        <Col span={24}>
          <Card title="最近练习" size="small">
            <Table
              size="small" rowKey="id"
              dataSource={data.recent}
              pagination={false}
              columns={[
                { title: '题目', dataIndex: 'title', render: (v: string) => v || '自由练习' },
                { title: '类型', dataIndex: 'q_type', width: 100, render: (v: string) => Q_TYPE_LABEL[v] || v },
                {
                  title: '得分', dataIndex: 'score', width: 110,
                  render: (v: number | null, r: any) =>
                    v != null ? <b style={{ color: '#3562a7' }}>{v} / {r.full_score}</b> : <Tag>{r.status === 'failed' ? '失败' : '批改中'}</Tag>,
                },
                { title: '时间', dataIndex: 'created_at', width: 150, render: (v: string) => v?.slice(5, 16) },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
