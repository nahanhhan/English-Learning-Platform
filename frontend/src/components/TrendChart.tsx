import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { WORKSPACE_FONT_FAMILY, type Appearance } from '../appearance'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

interface TrendPoint {
  date: string
  exam_type: string
  q_type: string
  score: number
  full_score: number
  title: string
}

const LIGHT_PALETTE = ['#007aff', '#34c759', '#ff9500', '#af52de', '#5856d6']
const DARK_PALETTE = ['#0a84ff', '#30d158', '#ff9f0a', '#bf5af2', '#5e5ce6']

function hexWithAlpha(hex: string, alpha: number): string {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export default function TrendChart({ trend, appearance }: { trend: TrendPoint[]; appearance: Appearance }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!ref.current) return
    chartRef.current = echarts.init(ref.current)
    const ro = new ResizeObserver(() => chartRef.current?.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
      chartRef.current?.dispose()
    }
  }, [])

  useEffect(() => {
    if (!chartRef.current || !ref.current) return
    const colors = getComputedStyle(ref.current)
    const tone = (name: string) => colors.getPropertyValue(`--workspace-${name}`).trim()
    const palette = appearance === 'dark' ? DARK_PALETTE : LIGHT_PALETTE
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const byType: Record<string, [string, number, number, string][]> = {
      '六级翻译': [],
      '六级写作': [],
      '考研翻译': [],
      '考研应用文': [],
      '考研图表作文': [],
    }
    const keyOf = (t: TrendPoint) =>
      t.exam_type === 'cet6'
        ? (t.q_type === 'translation' ? '六级翻译' : '六级写作')
        : t.q_type === 'translation'
          ? '考研翻译'
          : t.q_type === 'small_writing'
            ? '考研应用文'
            : '考研图表作文'
    for (const t of trend) byType[keyOf(t)].push([t.date, t.score, t.full_score, t.title])

    const activeEntries = Object.entries(byType).filter(([, pts]) => pts.length > 0)
    const series = activeEntries.map(([name, pts], idx) => {
      const stroke = palette[idx % palette.length]
      return {
        name,
        type: 'line' as const,
        data: pts,
        symbol: 'circle',
        symbolSize: 7,
        connectNulls: true,
        smooth: 0.35,
        lineStyle: { width: 2.3, color: stroke },
        itemStyle: {
          color: tone('surface'),
          borderColor: stroke,
          borderWidth: 2.2,
        },
        emphasis: {
          scale: 1.3,
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: hexWithAlpha(stroke, appearance === 'dark' ? 0.24 : 0.18) },
            { offset: 1, color: hexWithAlpha(stroke, 0) },
          ]),
        },
      }
    })

    chartRef.current.setOption(
      {
        animation: !reducedMotion,
        animationDuration: 740,
        animationEasing: 'cubicOut',
        color: palette,
        textStyle: {
          fontFamily: WORKSPACE_FONT_FAMILY,
        },
        tooltip: {
          trigger: 'item',
          renderMode: 'richText',
          borderColor: tone('strong-line'),
          borderWidth: 1,
          backgroundColor: tone('surface'),
          textStyle: { color: tone('ink'), fontSize: 12, fontFamily: WORKSPACE_FONT_FAMILY },
          formatter: (p: any) =>
            `${p.seriesName}\n${p.data[0]} · ${p.data[3]}\n${p.data[1]} / ${p.data[2]} 分`,
        },
        legend: {
          top: 6,
          right: 12,
          icon: 'circle',
          itemWidth: 8,
          itemHeight: 8,
          itemGap: 14,
          textStyle: { fontSize: 12, color: tone('muted') },
        },
        grid: { left: 36, right: 20, top: 42, bottom: 28 },
        xAxis: {
          type: 'time',
          minInterval: 24 * 60 * 60 * 1000,
          axisLine: { lineStyle: { color: tone('line') } },
          axisTick: { show: false },
          axisLabel: { color: tone('subtle'), fontSize: 11, hideOverlap: true, formatter: '{MM}-{dd}' },
        },
        yAxis: {
          type: 'value',
          max: 15,
          interval: 5,
          splitLine: { lineStyle: { color: tone('line'), type: 'dashed' } },
          axisLabel: { color: tone('subtle'), fontSize: 11 },
        },
        dataZoom: [{ type: 'inside' }],
        series,
      },
      true,
    )
  }, [trend, appearance])

  return <div ref={ref} className="dashboard-chart" role="img" aria-label="各题型成绩随时间变化的折线图" />
}
