import {
  BookOpen, ChevronRight, FolderOpen, GraduationCap, Languages, LayoutGrid, Link2, MessageSquare,
  Moon, PanelLeft, PencilLine, Search, Settings2, SquarePen, Sun, X, type LucideIcon,
} from 'lucide-react'
import { useEffect, useId, useState, type RefObject } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import type { Appearance } from '../appearance'

interface WorkspacePage {
  path: string
  title: string
  Icon: LucideIcon
}

const home = { path: '/', title: '学习概览', Icon: LayoutGrid }
const settings = { path: '/settings', title: '设置', Icon: Settings2 }
const groups: { label: string; pages: WorkspacePage[] }[] = [
  { label: '练习', pages: [
    { path: '/practice/translation', title: '真题翻译', Icon: Languages },
    { path: '/short-translation', title: '短句翻译', Icon: MessageSquare },
    { path: '/practice/writing', title: '写作练习', Icon: PencilLine },
  ] },
  { label: '词汇', pages: [
    { path: '/vocab', title: '背单词', Icon: BookOpen },
    { path: '/phrases', title: '背短语', Icon: Link2 },
    { path: '/classroom', title: '课内生词和短语', Icon: GraduationCap },
    { path: '/accumulation', title: '平时单词短语积累', Icon: FolderOpen },
  ] },
]

export const workspacePages = [home, ...groups.flatMap(group => group.pages), settings]

export function RailIcon({ icon: Icon, size = 14 }: { icon: LucideIcon; size?: number }) {
  return <Icon size={size} strokeWidth={1.45} absoluteStrokeWidth aria-hidden="true" />
}

export function WorkspaceToolbar({ onOpenJump, onOpenMenu }: { onOpenJump: () => void; onOpenMenu?: () => void }) {
  return (
    <header className={onOpenMenu ? 'workspace-toolbar workspace-mobile-header' : 'workspace-toolbar'}>
      {onOpenMenu && (
        <button className="rail-icon-button" type="button" aria-label="打开页面导航" title="打开页面导航"
          aria-haspopup="dialog" aria-controls="workspace-mobile-menu" onClick={onOpenMenu}>
          <RailIcon icon={PanelLeft} size={17} />
        </button>
      )}
      <Link className="workspace-brand" to="/">
        <span className="workspace-mark"><RailIcon icon={BookOpen} size={15} /></span>
        <span>英语学习平台</span>
      </Link>
      <div className="workspace-toolbar-actions">
        <button className="rail-icon-button" type="button" aria-label="快速跳转" title="快速跳转（Ctrl / ⌘ + K）"
          aria-haspopup="dialog" aria-controls="workspace-page-jump" aria-keyshortcuts="Control+K Meta+K" onClick={onOpenJump}>
          <RailIcon icon={Search} size={15} />
        </button>
        {!onOpenMenu && (
          <Link className="rail-icon-button rail-primary-action" to="/practice/writing" aria-label="打开写作练习" title="打开写作练习">
            <RailIcon icon={SquarePen} size={14} />
          </Link>
        )}
      </div>
    </header>
  )
}

function PageLink({ page, onNavigate }: { page: WorkspacePage; onNavigate?: () => void }) {
  return (
    <NavLink className="workspace-nav-row" to={page.path} end onClick={onNavigate}>
      <RailIcon icon={page.Icon} />
      <span>{page.title}</span>
    </NavLink>
  )
}

export function WorkspaceNavigation({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation()
  const groupId = useId()
  const [collapsed, setCollapsed] = useState<string[]>([])

  useEffect(() => {
    const activeGroup = groups.find(group => group.pages.some(page => page.path === pathname))
    if (activeGroup) setCollapsed(current => current.includes(activeGroup.label)
      ? current.filter(label => label !== activeGroup.label) : current)
  }, [pathname])

  return (
    <nav className="workspace-navigation" aria-label="主要导航">
      <PageLink page={home} onNavigate={onNavigate} />
      {groups.map(({ label, pages }, index) => {
        const open = !collapsed.includes(label)
        const id = `${groupId}-group-${index}`
        return (
          <div className="workspace-nav-group" key={label}>
            <button className="workspace-nav-label" type="button" aria-expanded={open} aria-controls={id}
              onClick={() => setCollapsed(current => open ? [...current, label] : current.filter(item => item !== label))}>
              <span>{label}</span>
              <RailIcon icon={ChevronRight} size={11} />
            </button>
            <div className="workspace-nav-items" id={id} hidden={!open}>
              {pages.map(page => <PageLink key={page.path} page={page} onNavigate={onNavigate} />)}
            </div>
          </div>
        )
      })}
    </nav>
  )
}

export function WorkspaceFooter({ appearance, onAppearanceChange, onNavigate }: {
  appearance: Appearance
  onAppearanceChange: () => void
  onNavigate?: () => void
}) {
  const dark = appearance === 'dark'
  const label = dark ? '切换浅色' : '切换深色'
  return (
    <footer className="workspace-sidebar-footer">
      <PageLink page={settings} onNavigate={onNavigate} />
      <button className="rail-icon-button" type="button" aria-label={label} title={label} onClick={onAppearanceChange}>
        <RailIcon icon={dark ? Sun : Moon} size={15} />
      </button>
    </footer>
  )
}

export function WorkspacePageJump({ dialog }: { dialog: RefObject<HTMLDialogElement> }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [query, setQuery] = useState('')
  const results = workspacePages.filter(page => page.title.includes(query.trim()))

  function openPage(path: string) {
    dialog.current?.close()
    navigate(path)
  }

  return (
    <dialog className="workspace-page-jump" id="workspace-page-jump" ref={dialog} aria-label="快速跳转"
      onClose={() => setQuery('')} onClick={event => {
        if (event.target === event.currentTarget) dialog.current?.close()
      }}>
      <div className="workspace-jump-panel">
        <div className="workspace-jump-search">
          <RailIcon icon={Search} size={17} />
          <input value={query} onChange={event => setQuery(event.target.value)} aria-label="搜索页面" placeholder="搜索页面…"
            onKeyDown={event => {
              if (event.key !== 'Enter' || event.nativeEvent.isComposing || event.keyCode === 229 || !results[0]) return
              event.preventDefault()
              openPage(results[0].path)
            }} />
          <button className="rail-icon-button" type="button" aria-label="关闭快速跳转" onClick={() => dialog.current?.close()}>
            <RailIcon icon={X} size={15} />
          </button>
        </div>
        <div className="workspace-jump-results">
          {results.map((page, index) => (
            <button key={page.path} type="button" className="workspace-nav-row" aria-current={pathname === page.path ? 'page' : undefined}
              onClick={() => openPage(page.path)}>
              <RailIcon icon={page.Icon} />
              <span>{page.title}</span>
              {index === 0 && <kbd aria-hidden="true">Enter</kbd>}
            </button>
          ))}
          {results.length === 0 && <p role="status">没有匹配的页面</p>}
        </div>
      </div>
    </dialog>
  )
}
