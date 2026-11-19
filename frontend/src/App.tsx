import { X } from 'lucide-react'
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import ErrorBoundary from './ErrorBoundary'
import type { Appearance } from './appearance'
import AppIcon from './components/AppIcon'
import {
  WorkspaceCollapsedBar,
  WorkspaceFooter,
  WorkspaceNavigation,
  WorkspacePageJump,
  WorkspaceToolbar,
  groupLabelForPath,
  workspacePages,
} from './components/WorkspaceNavigation'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Practice = lazy(() => import('./pages/Practice'))
const Vocab = lazy(() => import('./pages/Vocab'))
const Phrases = lazy(() => import('./pages/Phrases'))
const Settings = lazy(() => import('./pages/Settings'))
const Classroom = lazy(() => import('./pages/Classroom'))
const ShortTranslation = lazy(() => import('./pages/ShortTranslation'))

const SIDEBAR_COLLAPSED_KEY = 'elp-sidebar-collapsed'

function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

interface WorkspaceAppearance {
  appearance: Appearance
  onAppearanceChange: () => void
}

export default function App({ appearance, onAppearanceChange }: WorkspaceAppearance) {
  const { pathname } = useLocation()
  const menu = useRef<HTMLDialogElement>(null)
  const main = useRef<HTMLElement>(null)
  const jumpTriggerRef = useRef<HTMLElement | null>(null)
  const [jumpOpen, setJumpOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsed)
  const [collapsedGroups, setCollapsedGroups] = useState<string[]>([])
  const title = workspacePages.find(({ path }) => path === pathname)?.title

  useEffect(() => {
    document.title = title ? `${title} · 英语学习平台` : '英语学习平台'
  }, [title])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? '1' : '0')
    } catch {
      // 存储不可用时仅在本次会话维持折叠状态。
    }
  }, [sidebarCollapsed])

  const ensureGroupExpandedForPath = useCallback((targetPath: string) => {
    const groupLabel = groupLabelForPath(targetPath)
    if (!groupLabel) return
    setCollapsedGroups(current =>
      current.includes(groupLabel) ? current.filter(label => label !== groupLabel) : current,
    )
  }, [])

  useEffect(() => {
    ensureGroupExpandedForPath(pathname)
  }, [pathname, ensureGroupExpandedForPath])

  const openJump = useCallback((trigger?: HTMLElement | null) => {
    jumpTriggerRef.current =
      trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null)
    menu.current?.close()
    setJumpOpen(true)
  }, [])

  const closeJump = useCallback((restoreFocus = true) => {
    setJumpOpen(false)
    const trigger = jumpTriggerRef.current
    jumpTriggerRef.current = null
    if (restoreFocus && trigger && trigger.isConnected) {
      requestAnimationFrame(() => trigger.focus())
    }
  }, [])

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return
      const key = event.key.toLowerCase()
      if (key === 'k') {
        event.preventDefault()
        if (jumpOpen) closeJump(true)
        else openJump()
      } else if (event.key === '\\') {
        event.preventDefault()
        setSidebarCollapsed(current => !current)
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [jumpOpen, openJump, closeJump])

  const toggleGroup = (label: string) => {
    setCollapsedGroups(current =>
      current.includes(label) ? current.filter(item => item !== label) : [...current, label],
    )
  }

  const closeMenu = () => menu.current?.close()

  return (
    <div className="workspace">
      <a
        className="skip-navigation"
        href="#workspace-content"
        onClick={event => {
          event.preventDefault()
          main.current?.focus()
        }}
      >
        跳到主要内容
      </a>

      <aside
        className={sidebarCollapsed ? 'workspace-sidebar is-collapsed' : 'workspace-sidebar'}
        aria-hidden={sidebarCollapsed}
      >
        <WorkspaceToolbar
          onOpenJump={openJump}
          onCollapseSidebar={() => setSidebarCollapsed(true)}
        />
        <WorkspaceNavigation
          collapsedGroups={collapsedGroups}
          onToggleGroup={toggleGroup}
          enableIndicator
          sidebarCollapsed={sidebarCollapsed}
        />
        <WorkspaceFooter appearance={appearance} onAppearanceChange={onAppearanceChange} />
      </aside>

      <WorkspaceToolbar onOpenJump={openJump} onOpenMenu={() => menu.current?.showModal()} />

      <dialog
        className="workspace-menu"
        id="workspace-mobile-menu"
        ref={menu}
        aria-labelledby="workspace-menu-title"
        onClick={event => {
          if (event.target === event.currentTarget) closeMenu()
        }}
      >
        <div className="workspace-menu-sheet">
          <div className="workspace-menu-header">
            <h2 id="workspace-menu-title">页面导航</h2>
            <button
              className="rail-icon-button ap-press"
              type="button"
              aria-label="关闭页面导航"
              onClick={closeMenu}
            >
              <AppIcon icon={X} size={17} />
            </button>
          </div>
          <WorkspaceNavigation
            collapsedGroups={collapsedGroups}
            onToggleGroup={toggleGroup}
            onNavigate={closeMenu}
          />
          <WorkspaceFooter
            appearance={appearance}
            onAppearanceChange={onAppearanceChange}
            onNavigate={closeMenu}
          />
        </div>
      </dialog>

      <WorkspacePageJump
        open={jumpOpen}
        onClose={closeJump}
        onSelectPath={ensureGroupExpandedForPath}
      />

      <main className="workspace-content" id="workspace-content" ref={main} tabIndex={-1}>
        {sidebarCollapsed && (
          <WorkspaceCollapsedBar
            onExpandSidebar={() => setSidebarCollapsed(false)}
            onOpenJump={openJump}
          />
        )}
        <ErrorBoundary key={pathname}>
          <Suspense
            fallback={
              <div className="page route-placeholder" role="status">
                正在打开{title || '学习概览'}…
              </div>
            }
          >
            <div className="workspace-view-stage" key={pathname}>
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
            </div>
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  )
}
