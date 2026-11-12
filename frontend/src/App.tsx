import {
  AppstoreOutlined, BookOutlined, EditOutlined, FolderOpenOutlined, FontSizeOutlined,
  LinkOutlined, MenuOutlined, MessageOutlined, MoonOutlined, ReadOutlined, SettingOutlined,
  SunOutlined, TranslationOutlined,
} from '@ant-design/icons'
import { Suspense, lazy, useEffect, useRef } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import ErrorBoundary from './ErrorBoundary'
import type { Appearance } from './appearance'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Practice = lazy(() => import('./pages/Practice'))
const Vocab = lazy(() => import('./pages/Vocab'))
const Phrases = lazy(() => import('./pages/Phrases'))
const Settings = lazy(() => import('./pages/Settings'))
const Classroom = lazy(() => import('./pages/Classroom'))
const ShortTranslation = lazy(() => import('./pages/ShortTranslation'))

const groups = [
  { label: '', links: [{ path: '/', title: '学习概览', Icon: AppstoreOutlined }] },
  { label: '练习', links: [
    { path: '/practice/translation', title: '真题翻译', Icon: TranslationOutlined },
    { path: '/short-translation', title: '短句翻译', Icon: MessageOutlined },
    { path: '/practice/writing', title: '写作练习', Icon: EditOutlined },
  ] },
  { label: '词汇', links: [
    { path: '/vocab', title: '背单词', Icon: FontSizeOutlined },
    { path: '/phrases', title: '背短语', Icon: LinkOutlined },
    { path: '/classroom', title: '课内生词和短语', Icon: ReadOutlined },
    { path: '/accumulation', title: '平时单词短语积累', Icon: FolderOpenOutlined },
  ] },
  { label: '', links: [{ path: '/settings', title: '设置', Icon: SettingOutlined }] },
]

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="workspace-navigation" aria-label="主要导航">
      {groups.map(({ label, links }) => (
        <div className="navigation-group" key={links[0].path}>
          {label && <p className="navigation-label">{label}</p>}
          {links.map(({ path, title, Icon }) => (
            <NavLink key={path} to={path} end onClick={onNavigate}>
              <Icon className="navigation-icon" aria-hidden="true" />
              <span>{title}</span>
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )
}

interface WorkspaceAppearance {
  appearance: Appearance
  onAppearanceChange: () => void
}

function AppearanceButton({ appearance, onAppearanceChange }: WorkspaceAppearance) {
  const dark = appearance === 'dark'
  return (
    <button className="workspace-appearance" type="button" onClick={onAppearanceChange}>
      {dark ? <SunOutlined aria-hidden="true" /> : <MoonOutlined aria-hidden="true" />}
      <span>{dark ? '切换浅色' : '切换深色'}</span>
    </button>
  )
}

function WorkspaceBrand() {
  return <NavLink className="workspace-brand" to="/">
    <span className="workspace-mark"><BookOutlined aria-hidden="true" /></span>
    <span>英语学习平台</span>
  </NavLink>
}

export default function App({ appearance, onAppearanceChange }: WorkspaceAppearance) {
  const { pathname } = useLocation()
  const menu = useRef<HTMLDialogElement>(null)
  const main = useRef<HTMLElement>(null)
  const title = groups.flatMap(group => group.links).find(({ path }) => path === pathname)?.title

  useEffect(() => {
    document.title = title ? `${title} · 英语学习平台` : '英语学习平台'
  }, [title])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="workspace">
      <a className="skip-navigation" href="#workspace-content" onClick={event => {
        event.preventDefault()
        main.current?.focus()
      }}>跳到主要内容</a>
      <aside className="workspace-sidebar">
        <WorkspaceBrand />
        <Navigation />
        <AppearanceButton appearance={appearance} onAppearanceChange={onAppearanceChange} />
      </aside>
      <div className="workspace-mobile-header">
        <WorkspaceBrand />
        <button className="workspace-menu-button" type="button" aria-haspopup="dialog" aria-controls="workspace-mobile-menu"
          onClick={() => menu.current?.showModal()}>
          <MenuOutlined aria-hidden="true" /> 页面导航
        </button>
      </div>
      <dialog className="workspace-menu" id="workspace-mobile-menu" ref={menu} aria-labelledby="workspace-menu-title">
        <div className="workspace-menu-header">
          <h2 id="workspace-menu-title">页面导航</h2>
          <button className="workspace-menu-button" type="button" onClick={() => menu.current?.close()}>关闭</button>
        </div>
        <Navigation onNavigate={() => menu.current?.close()} />
        <AppearanceButton appearance={appearance} onAppearanceChange={onAppearanceChange} />
      </dialog>
      <main className="workspace-content" id="workspace-content" ref={main} tabIndex={-1}>
        <ErrorBoundary key={pathname}>
          <Suspense fallback={<div className="page route-placeholder" role="status">正在打开{title || '学习概览'}…</div>}>
            <Routes>
              <Route path="/" element={<Dashboard appearance={appearance} />} />
              <Route path="/short-translation" element={<ShortTranslation />} />
              <Route path="/practice/translation" element={<Practice mode="translation" key="t" />} />
              <Route path="/practice/writing" element={<Practice mode="writing" key="w" />} />
              <Route path="/vocab" element={<Vocab />} />
              <Route path="/phrases" element={<Phrases />} />
              <Route path="/classroom" element={<Classroom key="classroom" />} />
              <Route path="/accumulation" element={<Classroom key="accumulation" library="accumulation" />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Dashboard appearance={appearance} />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  )
}
