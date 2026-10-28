import {
  BarChartOutlined,
  BookOutlined,
  EditOutlined,
  ReadOutlined,
  SettingOutlined,
  TranslationOutlined,
} from '@ant-design/icons'
import { Layout, Menu } from 'antd'
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, Route, Routes, useLocation } from 'react-router-dom'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Practice = lazy(() => import('./pages/Practice'))
const Vocab = lazy(() => import('./pages/Vocab'))
const Phrases = lazy(() => import('./pages/Phrases'))
const Settings = lazy(() => import('./pages/Settings'))
const Classroom = lazy(() => import('./pages/Classroom'))

const { Sider, Content, Header } = Layout

export default function App() {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  const selected = useMemo(() => {
    const p = location.pathname
    if (p.startsWith('/practice')) return p
    if (p.startsWith('/vocab')) return '/vocab'
    if (p.startsWith('/phrases')) return '/phrases'
    if (p.startsWith('/classroom')) return '/classroom'
    if (p.startsWith('/accumulation')) return '/accumulation'
    if (p.startsWith('/settings')) return '/settings'
    return '/'
  }, [location.pathname])

  // 路由级页面标题
  useEffect(() => {
    const p = location.pathname
    const names: [RegExp, string][] = [
      [/^\/$/, '学习概览'],
      [/^\/practice\/translation/, '翻译练习'],
      [/^\/practice\/writing/, '写作练习'],
      [/^\/vocab/, '背单词'],
      [/^\/phrases/, '背短语'],
      [/^\/classroom/, '课内生词和短语'],
      [/^\/accumulation/, '平时单词短语积累'],
      [/^\/settings/, '设置'],
    ]
    const name = names.find(([re]) => re.test(p))?.[1]
    document.title = name ? `${name} · 英语学习平台` : '英语学习平台'
  }, [location.pathname])

  // 小窗口自动折叠侧栏
  useEffect(() => {
    const onResize = () => setCollapsed(window.innerWidth < 1000)
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const items = [
    { key: '/', icon: <BarChartOutlined />, label: <Link to="/">学习概览</Link> },
    { key: '/practice/translation', icon: <TranslationOutlined />, label: <Link to="/practice/translation">翻译练习</Link> },
    { key: '/practice/writing', icon: <EditOutlined />, label: <Link to="/practice/writing">写作练习</Link> },
    { key: '/vocab', icon: <BookOutlined />, label: <Link to="/vocab">背单词</Link> },
    { key: '/phrases', icon: <ReadOutlined />, label: <Link to="/phrases">背短语</Link> },
    { key: '/classroom', icon: <BookOutlined />, label: <Link to="/classroom">课内生词和短语</Link> },
    { key: '/accumulation', icon: <ReadOutlined />, label: <Link to="/accumulation">平时单词短语积累</Link> },
    { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        theme="light"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={200}
        style={{ borderRight: '1px solid #eef0f3' }}
      >
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            fontWeight: 700,
            fontSize: collapsed ? 16 : 15,
            color: '#3562a7',
          }}
        >
          <span style={{ fontSize: 20 }}>📘</span>
          {!collapsed && '英语学习平台'}
        </div>
        <Menu mode="inline" selectedKeys={[selected]} items={items} style={{ borderInlineEnd: 'none' }} />
      </Sider>
      <Layout>
        <Content>
          <Suspense
            fallback={
              <div style={{ padding: 80, textAlign: 'center', color: '#999' }}>加载中…</div>
            }
          >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/practice/translation" element={<Practice mode="translation" key="t" />} />
              <Route path="/practice/writing" element={<Practice mode="writing" key="w" />} />
              <Route path="/vocab" element={<Vocab />} />
              <Route path="/phrases" element={<Phrases />} />
              <Route path="/classroom" element={<Classroom key="classroom" />} />
              <Route path="/accumulation" element={<Classroom key="accumulation" library="accumulation" />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Dashboard />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  )
}
