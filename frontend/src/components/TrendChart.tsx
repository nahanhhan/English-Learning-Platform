import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { Appearance } from '../appearance'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

interface TrendPoint {
  date: string
  exam_type: string
  q_type: string
  score: number
  full_score: number
  title: string
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
    const byType: Record<string, [string, number, number, string][]> = {
      '六级翻译': [], '六级写作': [], '考研翻译': [], '考研应用文': [], '考研图表作文': [],
    }
    const keyOf = (t: TrendPoint) =>
      t.exam_type === 'cet6' ? (t.q_type === 'translation' ? '六级翻译' : '六级写作')
        : t.q_type === 'translation' ? '考研翻译' : t.q_type === 'small_writing' ? '考研应用文' : '考研图表作文'
    for (const t of trend) byType[keyOf(t)].push([t.date, t.score, t.full_score, t.title])

    const series = Object.entries(byType)
      .filter(([, pts]) => pts.length > 0)
      .map(([name, pts]) => ({
        name, type: 'line' as const, data: pts, symbolSize: 5,
        connectNulls: true, smooth: true,
        lineStyle: { width: 1.8 },
      }))

    chartRef.current.setOption(
      {
        animation: false,
        color: appearance === 'dark'
          ? ['#a19af9', '#79c4b3', '#91acd8', '#d5aa77', '#c397cf']
          : ['#6558cb', '#368471', '#4877b7', '#9d692f', '#965aab'],
        tooltip: {
          trigger: 'item',
          renderMode: 'richText',
          borderColor: tone('strong-line'),
          backgroundColor: tone('raised'),
          textStyle: { color: tone('ink'), fontSize: 12 },
          formatter: (p: any) =>
            `${p.seriesName}\n${p.data[0]} · ${p.data[3]}\n${p.data[1]} / ${p.data[2]} 分`,
        },
        legend: { top: 8, left: 12, itemWidth: 15, itemHeight: 7, textStyle: { fontSize: 11, color: tone('muted') } },
        grid: { left: 36, right: 23, top: 40, bottom: 31 },
        xAxis: {
          type: 'time',
          minInterval: 24 * 60 * 60 * 1000,
          axisLine: { lineStyle: { color: tone('line') } },
          axisTick: { show: false },
          axisLabel: { color: tone('muted'), fontSize: 11, hideOverlap: true, formatter: '{MM}-{dd}' },
        },
        yAxis: {
          type: 'value', max: 15, interval: 5,
          splitLine: { lineStyle: { color: tone('line') } },
          axisLabel: { color: tone('muted'), fontSize: 11 },
        },
        dataZoom: [{ type: 'inside' }],
        series,
      },
      true,
    )
  }, [trend, appearance])

  return <div ref={ref} className="dashboard-chart" role="img" aria-label="各题型成绩随时间变化的折线图" />
}
