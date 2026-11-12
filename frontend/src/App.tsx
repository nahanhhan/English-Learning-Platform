import { X } from 'lucide-react'
import { Suspense, lazy, useEffect, useRef } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import ErrorBoundary from './ErrorBoundary'
import type { Appearance } from './appearance'
import { RailIcon, WorkspaceFooter, WorkspaceNavigation, WorkspacePageJump, WorkspaceToolbar, workspacePages } from './components/WorkspaceNavigation'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Practice = lazy(() => import('./pages/Practice'))
const Vocab = lazy(() => import('./pages/Vocab'))
const Phrases = lazy(() => import('./pages/Phrases'))
const Settings = lazy(() => import('./pages/Settings'))
const Classroom = lazy(() => import('./pages/Classroom'))
const ShortTranslation = lazy(() => import('./pages/ShortTranslation'))

interface WorkspaceAppearance {
  appearance: Appearance
  onAppearanceChange: () => void
}

export default function App({ appearance, onAppearanceChange }: WorkspaceAppearance) {
  const { pathname } = useLocation()
  const menu = useRef<HTMLDialogElement>(null)
  const jump = useRef<HTMLDialogElement>(null)
  const main = useRef<HTMLElement>(null)
  const title = workspacePages.find(({ path }) => path === pathname)?.title

  useEffect(() => {
    document.title = title ? `${title} · 英语学习平台` : '英语学习平台'
  }, [title])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.key.toLowerCase() !== 'k') return
      event.preventDefault()
      menu.current?.close()
      jump.current?.showModal()
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  const openJump = () => jump.current?.showModal()
  const closeMenu = () => menu.current?.close()

  return (
    <div className="workspace">
      <a className="skip-navigation" href="#workspace-content" onClick={event => {
        event.preventDefault()
        main.current?.focus()
      }}>跳到主要内容</a>
      <aside className="workspace-sidebar">
        <WorkspaceToolbar onOpenJump={openJump} />
        <WorkspaceNavigation />
        <WorkspaceFooter appearance={appearance} onAppearanceChange={onAppearanceChange} />
      </aside>
      <WorkspaceToolbar onOpenJump={openJump} onOpenMenu={() => menu.current?.showModal()} />
      <dialog className="workspace-menu" id="workspace-mobile-menu" ref={menu} aria-labelledby="workspace-menu-title"
        onClick={event => {
          if (event.target === event.currentTarget) closeMenu()
        }}>
        <div className="workspace-menu-sheet">
          <div className="workspace-menu-header">
            <h2 id="workspace-menu-title">页面导航</h2>
            <button className="rail-icon-button" type="button" aria-label="关闭页面导航" onClick={closeMenu}><RailIcon icon={X} size={17} /></button>
          </div>
          <WorkspaceNavigation onNavigate={closeMenu} />
          <WorkspaceFooter appearance={appearance} onAppearanceChange={onAppearanceChange} onNavigate={closeMenu} />
        </div>
      </dialog>
      <WorkspacePageJump dialog={jump} />
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
