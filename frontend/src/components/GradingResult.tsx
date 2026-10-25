import {
  CheckCircleOutlined,
  EditOutlined,
  FileTextOutlined,
  StarOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, Collapse, Descriptions, Empty, Progress, Space, Tag, Tooltip, message } from 'antd'
import { useMemo } from 'react'
import { post } from '../api'
import type { Grading } from '../api'

const DIM_NAMES: Record<string, string> = {
  accuracy: '忠实准确',
  language: '语言质量',
  fluency: '表达流畅',
  task: '切题与要点',
  organization: '结构与衔接',
}

function scoreColor(pct: number) {
  if (pct >= 0.85) return '#52c41a'
  if (pct >= 0.7) return '#3562a7'
  if (pct >= 0.5) return '#e6a23c'
  return '#f5222d'
}

function ScoreHeader({ grading }: { grading: Grading }) {
  const pct = grading.full_score ? grading.score / grading.full_score : 0
  const result = grading.result as any
  const dims = result?.dimensions || {}
  return (
    <div style={{ display: 'flex', gap: 28, alignItems: 'center', flexWrap: 'wrap' }}>
      <div className="score-ring">
        <Progress
          type="circle"
          size={110}
          percent={Math.round(pct * 100)}
          strokeColor={scoreColor(pct)}
          format={() => (
            <div>
              <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1.1 }}>
                {grading.score}
                <span style={{ fontSize: 13, color: '#999' }}> / {grading.full_score}</span>
              </div>
            </div>
          )}
        />
      </div>
      <div style={{ flex: 1, minWidth: 260 }}>
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="分数档">
            <Tag color={scoreColor(pct) === '#f5222d' ? 'red' : 'blue'}>{String(result?.band || '—')}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="批改模型">
            {grading.mock ? <Tag color="orange">模拟批改</Tag> : <Tag>{grading.provider} · {grading.model}</Tag>}
          </Descriptions.Item>
        </Descriptions>
        <div style={{ display: 'flex', gap: 18, marginTop: 6, flexWrap: 'wrap' }}>
          {Object.entries(dims).map(([k, v]) => (
            <Tooltip key={k} title={`${DIM_NAMES[k] || k}（5 分制）`}>
              <div style={{ minWidth: 120 }}>
                <div style={{ fontSize: 12, color: '#888', marginBottom: 2 }}>{DIM_NAMES[k] || k}</div>
                <Progress percent={Number(v) * 20} size={['100%', 6]} showInfo={false} strokeColor={scoreColor(Number(v) / 5)} />
                <span style={{ fontSize: 12 }}>{Number(v)} / 5</span>
              </div>
            </Tooltip>
          ))}
        </div>
      </div>
    </div>
  )
}

function Fragment({ text }: { text: string }) {
  return (
    <span style={{ background: '#f0f2f5', borderRadius: 4, padding: '1px 6px', fontFamily: 'inherit' }}>
      {text}
    </span>
  )
}

export default function GradingResult({
  grading,
  onChanged,
}: {
  grading: Grading | null
  onChanged?: () => void
}) {
  const isTranslation = useMemo(() => {
    const r = grading?.result as any
    return r && 'improved_version' in r
  }, [grading])

  if (!grading) return <Empty description="还没有批改结果" />

  const r = grading.result as any
  if (!r) {
    return (
      <Card>
        <Empty description={grading.error || '批改结果为空'} />
      </Card>
    )
  }

  const isTrans = isTranslation

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {r.word_warnings?.length > 0 && (
        <Alert type="warning" showIcon message="字数提示" description={r.word_warnings.join('；')} />
      )}
      <Card>
        <ScoreHeader grading={grading} />
        <div style={{ marginTop: 14, color: 'rgba(0,0,0,0.75)', lineHeight: 1.8 }}>
          {r.overall_comment}
        </div>
      </Card>

      {/* 错误列表 */}
      {r.errors?.length > 0 && (
        <Card title={`逐处批析（${r.errors.length}）`} size="small">
          {r.errors.map((e: any, i: number) => (
            <div className="error-item" key={i}>
              <Space wrap size={8} style={{ marginBottom: 4 }}>
                <Tag color="orange">{e.issue_type || '问题'}</Tag>
                {e.fragment && <Fragment text={e.fragment} />}
              </Space>
              <div style={{ fontSize: 13.5, lineHeight: 1.7 }}>{e.explanation}</div>
              {(e.suggestion || e.correction) && (
                <div style={{ fontSize: 13.5, marginTop: 4 }}>
                  <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
                  <b>建议：</b>
                  <span style={{ color: '#2b7a0b' }}>{e.suggestion || e.correction}</span>
                </div>
              )}
            </div>
          ))}
        </Card>
      )}

      {/* 翻译特有 */}
      {isTrans && (
        <>
          {r.good_points?.length > 0 && (
            <Card title="亮点" size="small">
              {r.good_points.map((g: string, i: number) => (
                <div className="good-item" key={i} style={{ fontSize: 13.5 }}>{g}</div>
              ))}
            </Card>
          )}
          <Card title={<><EditOutlined /> 优化译文</>} size="small">
            <div className="source-text">{r.improved_version}</div>
          </Card>
          {r.key_notes?.length > 0 && (
            <Card title={<><StarOutlined /> 关键表达点拨</>} size="small">
              <Descriptions column={1} size="small">
                {r.key_notes.map((k: any, i: number) => (
                  <Descriptions.Item key={i} label={<Fragment text={k.expr} />}>
                    {k.note}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </Card>
          )}
        </>
      )}

      {/* 写作特有 */}
      {!isTrans && (
        <>
          {r.paragraph_comments?.length > 0 && (
            <Card title="逐段点评" size="small">
              {r.paragraph_comments.map((p: any, i: number) => (
                <div key={i} style={{ marginBottom: 10 }}>
                  <Tag>第 {p.paragraph} 段</Tag>
                  <span style={{ fontSize: 13.5, lineHeight: 1.7 }}>{p.comment}</span>
                </div>
              ))}
            </Card>
          )}
          {r.vocab_upgrades?.length > 0 && (
            <Card title={<><StarOutlined /> 词汇升级建议</>} size="small">
              <Descriptions column={1} size="small">
                {r.vocab_upgrades.map((v: any, i: number) => (
                  <Descriptions.Item key={i} label={<Space size={6}><Fragment text={v.original} />→</Space>}>
                    <b style={{ color: '#2b7a0b' }}>{v.upgrade}</b>
                    <span style={{ color: '#888' }}>　{v.note}</span>
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </Card>
          )}
          {r.structure_advice && (
            <Card title="结构建议" size="small">
              <div style={{ fontSize: 13.5, lineHeight: 1.8 }}>{r.structure_advice}</div>
            </Card>
          )}
          <Collapse
            items={[
              r.polished_version && {
                key: 'polished',
                label: <><EditOutlined /> 润色版全文</>,
                children: <div className="source-text">{r.polished_version}</div>,
              },
              r.model_essay && {
                key: 'model',
                label: <><FileTextOutlined /> 参考范文</>,
                children: <div className="source-text">{r.model_essay}</div>,
              },
            ].filter(Boolean) as any}
          />
        </>
      )}
    </Space>
  )
}
