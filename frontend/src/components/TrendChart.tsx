import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, BarChart, GridComponent, LegendComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

export default function TrendChart({ trend }: { trend: any[] }) {
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
    if (!chartRef.current || !trend) return
    const byType: Record<string, any[]> = {
      '六级翻译': [], '六级写作': [], '考研翻译': [], '考研应用文': [], '考研图表作文': [],
    }
    const keyOf = (t: any) =>
      t.exam_type === 'cet6' ? (t.q_type === 'translation' ? '六级翻译' : '六级写作')
        : t.q_type === 'translation' ? '考研翻译' : t.q_type === 'small_writing' ? '考研应用文' : '考研图表作文'
    for (const t of trend) byType[keyOf(t)].push([t.date, t.score, t.full_score, t.title])

    const series = Object.entries(byType)
      .filter(([, pts]) => pts.length > 0)
      .map(([name, pts]) => ({
        name, type: 'line' as const, data: pts, symbolSize: 7,
        connectNulls: true, smooth: true,
        lineStyle: { width: 2 },
        tooltip: {
          valueFormatter: (v: any) => v,
        },
      }))

    chartRef.current.setOption(
      {
        tooltip: {
          trigger: 'item',
          formatter: (p: any) =>
            `${p.seriesName}<br/>${p.data[0]} · ${p.data[3]}<br/><b>${p.data[1]} / ${p.data[2]} 分</b>`,
        },
        legend: { top: 0, textStyle: { fontSize: 12 } },
        grid: { left: 42, right: 16, top: 34, bottom: 46 },
        xAxis: { type: 'time', axisLabel: { fontSize: 11 } },
        yAxis: { type: 'value', max: 15, axisLabel: { fontSize: 11 } },
        dataZoom: [{ type: 'inside' }],
        series,
      },
      true,
    )
  }, [trend])

  return <div ref={ref} style={{ width: '100%', height: 300 }} />
}
