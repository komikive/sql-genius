import { useCallback, useState } from 'react'
import type { Icon } from '@phosphor-icons/react'
import {
  ChatsTeardrop,
  Circuitry,
  Database,
  List,
  MagicWand,
  Planet,
  Sparkle,
  Brain,
} from '@phosphor-icons/react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import FadeContent from '@/components/FadeContent'
import { cn } from '@/lib/utils'

type NavItem = {
  to: string
  title: string
  icon: Icon
}

const navItems: NavItem[] = [
  { to: '/overview', title: '总览', icon: Planet },
  { to: '/workbench', title: '工作台', icon: ChatsTeardrop },
  { to: '/admin/datasources', title: '数据源', icon: Database },
  { to: '/admin/skills', title: '技能', icon: Brain },
  { to: '/admin/memory', title: '记忆', icon: Sparkle },
  { to: '/admin/qa', title: '问答案例', icon: Database },
  { to: '/admin/history', title: '分析任务', icon: MagicWand },
]

const primaryNavItems = navItems.slice(0, 2)
const assetNavItems = navItems.slice(2)

export function AppShell() {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const isWorkbench = location.pathname === '/workbench'

  const closeSidebar = useCallback(() => setSidebarOpen(false), [])

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-[var(--background)]">
      {sidebarOpen ? (
        <div
          className="fixed inset-0 z-40 bg-[rgba(17,24,39,0.18)] backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          onKeyDown={(e) => e.key === 'Escape' && setSidebarOpen(false)}
          role="button"
          tabIndex={-1}
          aria-label="关闭侧边栏"
        />
      ) : null}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[232px] flex-col border-r border-[color-mix(in_srgb,var(--line)_72%,transparent)] bg-[rgba(255,255,255,0.72)] backdrop-blur-2xl transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] lg:static lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <Link
          to="/"
          className="flex h-[64px] items-center gap-3 px-5 transition-opacity hover:opacity-88"
          onClick={closeSidebar}
        >
          <span className="flex size-8 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--primary)] shadow-[0_10px_22px_rgba(36,88,211,0.1)]">
            <Circuitry className="size-[16px]" weight="duotone" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold tracking-[-0.02em] text-[var(--foreground)]">
              SQL Genius
            </div>
          </div>
        </Link>

        <div className="mx-4 h-px bg-[var(--line)]" />

        <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="主导航">
          <NavSection
            items={primaryNavItems}
            label="工作区"
            closeSidebar={closeSidebar}
            offset={0}
          />
          <NavSection
            items={assetNavItems}
            label="资产治理"
            closeSidebar={closeSidebar}
            offset={primaryNavItems.length}
          />
        </nav>

        <div className="border-t border-[var(--line)] px-4 py-3">
          <div className="flex items-center gap-2 rounded-2xl border border-[var(--line)] bg-white/56 px-3 py-2">
            <span className="status-dot" />
            <span className="text-[11px] text-[var(--muted-foreground)]">系统运行中</span>
          </div>
        </div>
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-12 items-center gap-3 border-b border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_84%,transparent)] px-4 backdrop-blur-xl lg:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="inline-flex size-8 items-center justify-center rounded-lg border border-[var(--line)] text-[var(--foreground-soft)]"
            aria-label="打开侧边栏"
          >
            <List className="size-[16px]" />
          </button>
          <Link to="/" className="text-[13px] font-semibold text-[var(--foreground)]">
            SQL Genius
          </Link>
        </header>

        <main id="main-content" className="flex-1 overflow-y-auto">
          {isWorkbench ? (
            <Outlet />
          ) : (
            <div className="mx-auto max-w-[1120px] space-y-5 px-5 py-6 sm:px-6 lg:px-7 lg:py-7">
              <Outlet />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

function NavSection({
  items,
  label,
  closeSidebar,
  offset,
}: {
  items: NavItem[]
  label: string
  closeSidebar: () => void
  offset: number
}) {
  return (
    <div className="space-y-1 pb-4 last:pb-0">
      <div className="px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
        {label}
      </div>
      <div className="space-y-0.5">
        {items.map((item, index) => {
          const Icon = item.icon
          return (
            <FadeContent key={item.to} delay={(offset + index) * 42} duration={320}>
              <NavLink
                to={item.to}
                onClick={closeSidebar}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-[1rem] px-3 py-2 text-[13px] font-medium transition-all duration-200',
                    isActive
                      ? 'bg-[color-mix(in_srgb,var(--primary)_9%,white)] text-[var(--foreground)] shadow-[inset_0_1px_0_rgba(255,255,255,0.58),0_1px_4px_rgba(36,88,211,0.06)]'
                      : 'text-[var(--foreground-soft)] hover:bg-white/58 hover:text-[var(--foreground)]',
                  )
                }
              >
                <Icon className="size-[17px] shrink-0" />
                {item.title}
              </NavLink>
            </FadeContent>
          )
        })}
      </div>
    </div>
  )
}
