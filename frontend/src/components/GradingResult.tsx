import { Alert, Card, Collapse, Descriptions, Empty, Space, Tag, Tooltip } from 'antd'
import { CheckCircle2, FileText, PencilLine, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { Grading } from '../api'
import AppIcon from './AppIcon'

const DIM_NAMES: Record<string, string> = {
  accuracy: '忠实准确',
  language: '语言质量',
  fluency: '表达流畅',
  task: '切题与要点',
  organization: '结构与衔接',
  structure: '结构与衔接',
}

const RING_CIRCUMFERENCE = 2 * Math.PI * 42

function scoreTone(pct: number) {
  if (pct >= 0.85) return { color: 'var(--workspace-success)', bg: 'var(--workspace-success-bg)' }
  if (pct >= 0.7) return { color: 'var(--workspace-accent)', bg: 'var(--workspace-accent-bg)' }
  if (pct >= 0.5) return { color: 'var(--workspace-warning)', bg: 'var(--workspace-warning-bg)' }
  return { color: 'var(--workspace-error)', bg: 'var(--workspace-error-bg)' }
}

function ScoreHeader({ grading }: { grading: Grading }) {
  const pct = Math.max(0, Math.min(1, grading.full_score ? grading.score / grading.full_score : 0))
  const result = grading.result as any
  const dims = Object.entries(result?.dimensions || {})
  const tone = scoreTone(pct)

  const [animated, setAnimated] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setAnimated(true)
      return
    }
    setAnimated(false)
    let raf2 = 0
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setAnimated(true))
    })
    return () => {
      cancelAnimationFrame(raf1)
      cancelAnimationFrame(raf2)
    }
  }, [grading.id, grading.score])

  const targetOffset = RING_CIRCUMFERENCE * (1 - pct)

  return (
    <div className="grading-header-row">
      <div className="score-ring" role="img" aria-label={`得分 ${grading.score} / ${grading.full_score} 分`}>
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="42" fill="none" stroke="var(--workspace-raised)" strokeWidth="8" />
          <circle
            className="ap-ring-arc"
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke={tone.color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={RING_CIRCUMFERENCE}
            strokeDashoffset={animated ? targetOffset : RING_CIRCUMFERENCE}
          />
        </svg>
        <div className="score-ring-label">
          <span className="score-ring-value">{grading.score}</span>
          <span className="score-ring-total">/ {grading.full_score} 分</span>
        </div>
      </div>

      <div className="grading-header-meta">
        <div className="grading-badges">
          <span className="grading-pill" style={{ background: tone.bg, color: tone.color }}>
            {String(result?.band || '—')}
          </span>
          {grading.mock ? (
            <span
              className="grading-pill"
              style={{ background: 'var(--workspace-warning-bg)', color: 'var(--workspace-warning)' }}
            >
              模拟批改
            </span>
          ) : (
            <span className="grading-pill grading-pill-muted">
              {grading.provider} · {grading.model}
            </span>
          )}
        </div>

        {dims.length > 0 && (
          <div className="grading-dims-grid">
            {dims.map(([k, v], index) => {
              const score = Number(v)
              const dimTone = scoreTone(score / 5)
              const width = animated ? `${Math.min(100, Math.max(0, score * 20))}%` : '0%'
              return (
                <Tooltip key={k} title={`${DIM_NAMES[k] || k}（5 分制）`}>
                  <div>
                    <div className="grading-dim-head">
                      <span className="grading-dim-name">{DIM_NAMES[k] || k}</span>
                      <span className="grading-dim-score">{score} / 5</span>
                    </div>
                    <div className="grading-dim-track">
                      <div
                        className="grading-dim-fill ap-progress-fill"
                        style={{
                          width,
                          background: dimTone.color,
                          transitionDelay: `${80 + index * 70}ms`,
                        }}
                      />
                    </div>
                  </div>
                </Tooltip>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function Fragment({ text }: { text: string }) {
  return (
    <span
      style={{
        background: 'var(--workspace-surface)',
        border: '1px solid var(--workspace-line)',
        borderRadius: 6,
        padding: '1px 7px',
        fontFamily: 'inherit',
      }}
    >
      {text}
    </span>
  )
}

export default function GradingResult({
  grading,
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
        <div
          style={{
            marginTop: 18,
            paddingTop: 14,
            borderTop: '1px solid var(--workspace-line)',
            color: 'var(--workspace-ink)',
            lineHeight: 1.8,
          }}
        >
          {r.overall_comment}
        </div>
        {r.score_reason && (
          <div style={{ marginTop: 10, lineHeight: 1.8 }}>
            <b>评分依据：</b>
            {r.score_reason}
          </div>
        )}
        {(r.rubric_version?.startsWith('cet6-translation') ||
          r.rubric_version?.startsWith('cet6-writing') ||
          r.rubric_version?.startsWith('ky2-writing')) && (
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--workspace-muted)' }}>
            {r.rubric_version?.startsWith('ky2-writing')
              ? '依据考研英语（二）写作要求的训练估分；'
              : '依据公开六级标准的训练估分；'}
            三个维度仅作学习诊断，不相加决定总分。
          </div>
        )}
      </Card>

      {r.errors?.length > 0 && (
        <Card title={`逐处批析（${r.errors.length}）`} size="small">
          {r.errors.map((e: any, i: number) => (
            <div className="error-item" key={i}>
              <Space wrap size={8} style={{ marginBottom: 6 }}>
                <Tag color="orange">{e.issue_type || '问题'}</Tag>
                {e.fragment && <Fragment text={e.fragment} />}
              </Space>
              <div style={{ fontSize: 13.5, lineHeight: 1.7 }}>{e.explanation}</div>
              {(e.suggestion || e.correction) && (
                <div style={{ fontSize: 13.5, marginTop: 6, display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                  <AppIcon
                    icon={CheckCircle2}
                    size={15}
                    style={{ color: 'var(--workspace-success)', marginTop: 3, flexShrink: 0 }}
                  />
                  <span>
                    <b>建议：</b>
                    <span style={{ color: 'var(--workspace-success)' }}>{e.suggestion || e.correction}</span>
                  </span>
                </div>
              )}
            </div>
          ))}
        </Card>
      )}

      {isTrans && (
        <>
          {r.good_points?.length > 0 && (
            <Card title="亮点" size="small">
              {r.good_points.map((g: string, i: number) => (
                <div className="good-item" key={i} style={{ fontSize: 13.5 }}>
                  {g}
                </div>
              ))}
            </Card>
          )}
          <Card
            title={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                <AppIcon icon={PencilLine} size={15} />
                优化译文
              </span>
            }
            size="small"
          >
            <div className="source-text">{r.improved_version}</div>
          </Card>
          {r.key_notes?.length > 0 && (
            <Card
              title={
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                  <AppIcon icon={Sparkles} size={15} />
                  关键表达点拨
                </span>
              }
              size="small"
            >
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
          {r.optional_suggestions?.length > 0 && (
            <Card title="可选表达建议（不作为错误扣分）" size="small">
              {r.optional_suggestions.map((item: any, i: number) => (
                <div key={i} style={{ marginBottom: 10, lineHeight: 1.7 }}>
                  {item.original && <Fragment text={item.original} />}
                  {item.suggestion && <span> → {item.suggestion}</span>}
                  {item.reason && <div>{item.reason}</div>}
                </div>
              ))}
            </Card>
          )}
          {r.vocab_upgrades?.length > 0 && (
            <Card
              title={
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                  <AppIcon icon={Sparkles} size={15} />
                  词汇升级建议
                </span>
              }
              size="small"
            >
              <Descriptions column={1} size="small">
                {r.vocab_upgrades.map((v: any, i: number) => (
                  <Descriptions.Item
                    key={i}
                    label={
                      <Space size={6}>
                        <Fragment text={v.original} />→
                      </Space>
                    }
                  >
                    <b style={{ color: 'var(--workspace-success)' }}>{v.upgrade}</b>
                    <span style={{ color: 'var(--workspace-muted)' }}>　{v.note}</span>
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
                label: (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                    <AppIcon icon={PencilLine} size={15} />
                    润色版全文
                  </span>
                ),
                children: <div className="source-text">{r.polished_version}</div>,
              },
              r.model_essay && {
                key: 'model',
                label: (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                    <AppIcon icon={FileText} size={15} />
                    参考范文
                  </span>
                ),
                children: <div className="source-text">{r.model_essay}</div>,
              },
            ].filter(Boolean) as any}
          />
        </>
      )}
    </Space>
  )
}
