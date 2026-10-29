import { Link, Outlet } from 'react-router'
import { Toaster } from 'sonner'

import { LogoMark } from '@/components/LogoMark'
import { ThemeToggle } from '@/components/ThemeToggle'
import { WorkspaceSwitcher } from '@/components/WorkspaceSwitcher'
import { useTheme } from '@/lib/useTheme'

export function AppShell() {
  const { preference, theme, cycle } = useTheme()

  return (
    <div className="flex h-svh flex-col overflow-hidden bg-background text-foreground">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-background px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="shrink-0 border-b bg-background/80 backdrop-blur">
        <div className="flex h-14 items-center gap-3 px-3 sm:px-4">
          <Link
            to="/"
            aria-label="DocQA home"
            className="flex shrink-0 items-center gap-2 rounded-md font-heading font-semibold tracking-tight focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <LogoMark />
            <span className="hidden sm:inline">DocQA</span>
            <span className="hidden rounded-full border px-1.5 py-px text-[0.6875rem] font-medium text-muted-foreground md:inline">
              Support Agent
            </span>
          </Link>
          <span className="h-5 w-px shrink-0 bg-border" aria-hidden />
          <WorkspaceSwitcher />
          <div className="ml-auto shrink-0">
            <ThemeToggle preference={preference} onCycle={cycle} />
          </div>
        </div>
      </header>
      <main id="main" className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </main>
      <Toaster theme={theme} position="bottom-right" closeButton richColors={false} />
    </div>
  )
}
