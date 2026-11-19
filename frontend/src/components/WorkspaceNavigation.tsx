import {
  BookOpen,
  ChevronRight,
  FolderOpen,
  GraduationCap,
  Languages,
  LayoutGrid,
  Link2,
  MessageSquare,
  Moon,
  PanelLeft,
  PanelLeftClose,
  PanelLeftOpen,
  PencilLine,
  Search,
  Settings2,
  Sun,
  X,
  type LucideIcon,
} from 'lucide-react'
import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import type { Appearance } from '../appearance'
import AppIcon from './AppIcon'

export interface WorkspacePage {
  path: string
  title: string
  group: string
  Icon: LucideIcon
}

const home: WorkspacePage = { path: '/', title: '学习概览', group: '首页', Icon: LayoutGrid }
const settings: WorkspacePage = { path: '/settings', title: '设置', group: '系统', Icon: Settings2 }
export const workspaceGroups: { label: string; pages: WorkspacePage[] }[] = [
  {
    label: '练习',
    pages: [
      { path: '/practice/translation', title: '真题翻译', group: '练习', Icon: Languages },
      { path: '/short-translation', title: '短句翻译', group: '练习', Icon: MessageSquare },
      { path: '/practice/writing', title: '写作练习', group: '练习', Icon: PencilLine },
    ],
  },
  {
    label: '词汇',
    pages: [
      { path: '/vocab', title: '背单词', group: '词汇', Icon: BookOpen },
      { path: '/phrases', title: '背短语', group: '词汇', Icon: Link2 },
      { path: '/classroom', title: '课内生词和短语', group: '词汇', Icon: GraduationCap },
      { path: '/accumulation', title: '平时单词短语积累', group: '词汇', Icon: FolderOpen },
    ],
  },
]

export const workspacePages: WorkspacePage[] = [
  home,
  ...workspaceGroups.flatMap(group => group.pages),
  settings,
]

export function groupLabelForPath(pathname: string): string | undefined {
  return workspaceGroups.find(group => group.pages.some(page => page.path === pathname))?.label
}

export function WorkspaceToolbar({
  onOpenJump,
  onOpenMenu,
  onCollapseSidebar,
}: {
  onOpenJump: (trigger?: HTMLElement | null) => void
  onOpenMenu?: () => void
  onCollapseSidebar?: () => void
}) {
  return (
    <header className={onOpenMenu ? 'workspace-toolbar workspace-mobile-header' : 'workspace-toolbar'}>
      {onOpenMenu && (
        <button
          className="rail-icon-button ap-press"
          type="button"
          aria-label="打开页面导航"
          title="打开页面导航"
          aria-haspopup="dialog"
          aria-controls="workspace-mobile-menu"
          onClick={onOpenMenu}
        >
          <AppIcon icon={PanelLeft} size={17} />
        </button>
      )}
      <Link className="workspace-brand ap-press" to="/">
        <span className="workspace-mark">
          <AppIcon icon={BookOpen} size={14} strokeWidth={1.9} />
        </span>
        <span>英语学习平台</span>
      </Link>
      <div className="workspace-toolbar-actions">
        <button
          className="rail-icon-button ap-press"
          type="button"
          aria-label="快速跳转"
          title="快速跳转 (Ctrl/⌘+K)"
          aria-haspopup="dialog"
          aria-controls="workspace-page-jump"
          aria-keyshortcuts="Control+K Meta+K"
          onClick={event => onOpenJump(event.currentTarget)}
        >
          <AppIcon icon={Search} size={15} />
        </button>
        {!onOpenMenu && onCollapseSidebar && (
          <button
            className="rail-icon-button ap-press"
            type="button"
            aria-label="收起侧栏"
            title="收起侧栏 (Ctrl/⌘+\)"
            aria-keyshortcuts="Control+\ Meta+\"
            onClick={onCollapseSidebar}
          >
            <AppIcon icon={PanelLeftClose} size={15} />
          </button>
        )}
      </div>
    </header>
  )
}

export function WorkspaceCollapsedBar({
  onExpandSidebar,
  onOpenJump,
}: {
  onExpandSidebar: () => void
  onOpenJump: (trigger?: HTMLElement | null) => void
}) {
  return (
    <div className="workspace-collapsed-bar ap-float-in">
      <button
        type="button"
        className="workspace-collapsed-pill ap-press"
        title="展开导航 (Ctrl/⌘+\)"
        aria-label="展开导航"
        aria-keyshortcuts="Control+\ Meta+\"
        onClick={onExpandSidebar}
      >
        <AppIcon icon={PanelLeftOpen} size={14} />
        <span>展开导航</span>
      </button>
      <button
        type="button"
        className="workspace-collapsed-pill ap-press"
        title="快速跳转 (Ctrl/⌘+K)"
        aria-haspopup="dialog"
        aria-controls="workspace-page-jump"
        aria-keyshortcuts="Control+K Meta+K"
        onClick={event => onOpenJump(event.currentTarget)}
      >
        <AppIcon icon={Search} size={13} />
        <span>快速跳转 Ctrl+K</span>
      </button>
    </div>
  )
}

function PageLink({ page, onNavigate }: { page: WorkspacePage; onNavigate?: () => void }) {
  return (
    <NavLink className="workspace-nav-row ap-press" to={page.path} end onClick={onNavigate}>
      <AppIcon icon={page.Icon} size={16} />
      <span>{page.title}</span>
    </NavLink>
  )
}

export function WorkspaceNavigation({
  collapsedGroups,
  onToggleGroup,
  onNavigate,
  enableIndicator = false,
  sidebarCollapsed = false,
}: {
  collapsedGroups: string[]
  onToggleGroup: (label: string) => void
  onNavigate?: () => void
  enableIndicator?: boolean
  sidebarCollapsed?: boolean
}) {
  const { pathname } = useLocation()
  const groupId = useId()
  const navRef = useRef<HTMLElement>(null)
  const hasPositionedRef = useRef(false)
  const [indicator, setIndicator] = useState<{ top: number; height: number; visible: boolean }>({
    top: 0,
    height: 36,
    visible: false,
  })
  const [skipTransition, setSkipTransition] = useState(true)

  useLayoutEffect(() => {
    if (!enableIndicator) return
    if (sidebarCollapsed) {
      hasPositionedRef.current = false
      return
    }
    const nav = navRef.current
    if (!nav) return

    const measure = () => {
      const activeEl = nav.querySelector<HTMLElement>(".workspace-nav-row[aria-current='page']")
      if (!activeEl) {
        setIndicator(prev => (prev.visible ? { ...prev, visible: false } : prev))
        return
      }
      const navRect = nav.getBoundingClientRect()
      const btnRect = activeEl.getBoundingClientRect()
      if (btnRect.height === 0 || navRect.width === 0) {
        setIndicator(prev => (prev.visible ? { ...prev, visible: false } : prev))
        return
      }
      const nextTop = btnRect.top - navRect.top
      const nextHeight = btnRect.height
      if (!hasPositionedRef.current) {
        hasPositionedRef.current = true
        setSkipTransition(true)
        setIndicator({ top: nextTop, height: nextHeight, visible: true })
        requestAnimationFrame(() => setSkipTransition(false))
      } else {
        setIndicator({ top: nextTop, height: nextHeight, visible: true })
      }
    }

    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(nav)
    return () => ro.disconnect()
  }, [enableIndicator, pathname, collapsedGroups, sidebarCollapsed])

  const indicatorStyle: CSSProperties = {
    opacity: indicator.visible ? 1 : 0,
    height: `${indicator.height}px`,
    transform: `translateY(${indicator.top}px)`,
    transition: skipTransition ? 'none' : undefined,
  }

  return (
    <nav
      ref={navRef}
      className={enableIndicator ? 'workspace-navigation has-indicator' : 'workspace-navigation'}
      aria-label="主要导航"
    >
      {enableIndicator && <div className="nav-active-indicator" style={indicatorStyle} aria-hidden="true" />}
      <div className="workspace-nav-root">
        <PageLink page={home} onNavigate={onNavigate} />
      </div>
      {workspaceGroups.map(({ label, pages }, index) => {
        const open = !collapsedGroups.includes(label)
        const id = `${groupId}-group-${index}`
        return (
          <div className="workspace-nav-group" key={label}>
            <button
              className="workspace-nav-label"
              type="button"
              aria-expanded={open}
              aria-controls={id}
              onClick={() => onToggleGroup(label)}
            >
              <span>{label}</span>
              <AppIcon icon={ChevronRight} size={12} />
            </button>
            <div className="workspace-nav-items" id={id} hidden={!open}>
              {pages.map(page => (
                <PageLink key={page.path} page={page} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        )
      })}
    </nav>
  )
}

export function WorkspaceFooter({
  appearance,
  onAppearanceChange,
  onNavigate,
}: {
  appearance: Appearance
  onAppearanceChange: () => void
  onNavigate?: () => void
}) {
  const dark = appearance === 'dark'
  const label = dark ? '切换浅色' : '切换深色'
  return (
    <footer className="workspace-sidebar-footer">
      <PageLink page={settings} onNavigate={onNavigate} />
      <button
        className="rail-icon-button ap-press"
        type="button"
        aria-label={label}
        title={label}
        onClick={onAppearanceChange}
      >
        <AppIcon icon={dark ? Sun : Moon} size={15} />
      </button>
    </footer>
  )
}

export function WorkspacePageJump({
  open,
  onClose,
  onSelectPath,
}: {
  open: boolean
  onClose: (restoreFocus?: boolean) => void
  onSelectPath: (path: string) => void
}) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const [rendered, setRendered] = useState(open)
  const [phase, setPhase] = useState<'closed' | 'open' | 'closing'>('closed')
  const inputRef = useRef<HTMLInputElement>(null)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const prevOpenRef = useRef(false)

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return workspacePages
    return workspacePages.filter(
      page => page.title.toLowerCase().includes(q) || page.group.toLowerCase().includes(q),
    )
  }, [query])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  useEffect(() => {
    if (activeIndex >= results.length) {
      setActiveIndex(Math.max(0, results.length - 1))
    }
  }, [results.length, activeIndex])

  useEffect(() => {
    clearTimeout(closeTimerRef.current)
    let raf1 = 0
    let raf2 = 0
    if (open && !prevOpenRef.current) {
      prevOpenRef.current = true
      setRendered(true)
      setQuery('')
      setActiveIndex(0)
      setPhase('closed')
      raf1 = requestAnimationFrame(() => {
        raf2 = requestAnimationFrame(() => {
          setPhase('open')
          inputRef.current?.focus()
        })
      })
    } else if (!open && prevOpenRef.current) {
      prevOpenRef.current = false
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      if (reduced) {
        setRendered(false)
        setPhase('closed')
      } else {
        setPhase('closing')
        closeTimerRef.current = setTimeout(() => {
          setRendered(false)
          setPhase('closed')
        }, 165)
      }
    }
    return () => {
      cancelAnimationFrame(raf1)
      cancelAnimationFrame(raf2)
      clearTimeout(closeTimerRef.current)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.isComposing) {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onEscape)
    return () => window.removeEventListener('keydown', onEscape)
  }, [open, onClose])

  function openPage(path: string) {
    onSelectPath(path)
    onClose(false)
    navigate(path)
  }

  if (!rendered) return null

  const backdropClass = [
    'ap-spotlight-backdrop',
    phase === 'open' ? 'is-open' : '',
    phase === 'closing' ? 'is-closing' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div
      className={backdropClass}
      id="workspace-page-jump"
      role="dialog"
      aria-modal="true"
      aria-label="快速跳转"
      onClick={event => {
        if (event.target === event.currentTarget) onClose(true)
      }}
    >
      <div className="ap-spotlight-panel ap-glass">
        <div className="workspace-jump-search">
          <AppIcon icon={Search} size={17} style={{ color: 'var(--workspace-accent)' }} />
          <input
            ref={inputRef}
            value={query}
            onChange={event => setQuery(event.target.value)}
            aria-label="搜索页面"
            placeholder="搜索页面或功能…"
            onKeyDown={event => {
              if (event.nativeEvent.isComposing || event.keyCode === 229) return
              if (event.key === 'Escape') {
                event.preventDefault()
                onClose(true)
                return
              }
              if (event.key === 'ArrowDown' && results.length > 0) {
                event.preventDefault()
                setActiveIndex(i => (i + 1) % results.length)
                return
              }
              if (event.key === 'ArrowUp' && results.length > 0) {
                event.preventDefault()
                setActiveIndex(i => (i - 1 + results.length) % results.length)
                return
              }
              if (event.key === 'Enter' && results[activeIndex]) {
                event.preventDefault()
                openPage(results[activeIndex].path)
              }
            }}
          />
          <kbd className="workspace-jump-esc" aria-hidden="true">
            Esc
          </kbd>
          <button
            className="rail-icon-button ap-press"
            type="button"
            aria-label="关闭快速跳转"
            onClick={() => onClose(true)}
          >
            <AppIcon icon={X} size={15} />
          </button>
        </div>

        <div className="workspace-jump-results" role="listbox" aria-label="页面搜索结果">
          {results.map((page, index) => {
            const active = index === activeIndex
            const current = pathname === page.path
            return (
              <button
                key={page.path}
                type="button"
                role="option"
                aria-selected={active}
                className={active ? 'workspace-jump-row is-active' : 'workspace-jump-row'}
                aria-current={current ? 'page' : undefined}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => openPage(page.path)}
              >
                <span className="workspace-jump-row-main">
                  <AppIcon icon={page.Icon} size={15} />
                  <span>{page.title}</span>
                </span>
                <span className="workspace-jump-row-meta">
                  {active ? 'Enter 打开' : page.group}
                </span>
              </button>
            )
          })}
          {results.length === 0 && (
            <p className="workspace-jump-empty" role="status">
              没有匹配的页面
            </p>
          )}
        </div>

        <div className="workspace-jump-footer" aria-hidden="true">
          <span>↑ ↓ 选择 · Enter 打开</span>
          <span>Ctrl / ⌘ + K</span>
        </div>
      </div>
    </div>
  )
}
