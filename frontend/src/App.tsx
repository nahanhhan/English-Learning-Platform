import { Suspense, lazy, useEffect, useRef } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import ErrorBoundary from './ErrorBoundary'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Practice = lazy(() => import('./pages/Practice'))
const Vocab = lazy(() => import('./pages/Vocab'))
const Phrases = lazy(() => import('./pages/Phrases'))
const Settings = lazy(() => import('./pages/Settings'))
const Classroom = lazy(() => import('./pages/Classroom'))
const ShortTranslation = lazy(() => import('./pages/ShortTranslation'))

const groups = [
  { label: '', links: [['/', '学习概览']] },
  { label: '练习', links: [['/practice/translation', '真题翻译'], ['/short-translation', '短句翻译'], ['/practice/writing', '写作练习']] },
  { label: '词汇', links: [['/vocab', '背单词'], ['/phrases', '背短语'], ['/classroom', '课内生词和短语'], ['/accumulation', '平时单词短语积累']] },
  { label: '', links: [['/settings', '设置']] },
]

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="workspace-navigation" aria-label="主要导航">
      {groups.map(({ label, links }) => (
        <div className="navigation-group" key={links[0][0]}>
          {label && <p className="navigation-label">{label}</p>}
          {links.map(([path, title]) => (
            <NavLink key={path} to={path} end onClick={onNavigate}>{title}</NavLink>
          ))}
        </div>
      ))}
    </nav>
  )
}

export default function App() {
  const { pathname } = useLocation()
  const menu = useRef<HTMLDialogElement>(null)
  const main = useRef<HTMLElement>(null)
  const title = groups.flatMap(group => group.links).find(([path]) => path === pathname)?.[1]

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
        <NavLink className="workspace-brand" to="/">英语学习平台</NavLink>
        <Navigation />
      </aside>
      <div className="workspace-mobile-header">
        <NavLink className="workspace-brand" to="/">英语学习平台</NavLink>
        <button className="workspace-menu-button" type="button" aria-haspopup="dialog" aria-controls="workspace-mobile-menu"
          onClick={() => menu.current?.showModal()}>
          页面导航
        </button>
      </div>
      <dialog className="workspace-menu" id="workspace-mobile-menu" ref={menu} aria-labelledby="workspace-menu-title">
        <div className="workspace-menu-header">
          <h2 id="workspace-menu-title">页面导航</h2>
          <button className="workspace-menu-button" type="button" onClick={() => menu.current?.close()}>关闭</button>
        </div>
        <Navigation onNavigate={() => menu.current?.close()} />
      </dialog>
      <main className="workspace-content" id="workspace-content" ref={main} tabIndex={-1}>
        <ErrorBoundary key={pathname}>
          <Suspense fallback={<div className="page route-placeholder" role="status">正在打开{title || '学习概览'}…</div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/short-translation" element={<ShortTranslation />} />
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
        </ErrorBoundary>
      </main>
    </div>
  )
}
