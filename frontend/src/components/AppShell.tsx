import { MessagesSquareIcon } from 'lucide-react'
import { Link, Outlet } from 'react-router'

import { WorkspaceSwitcher } from '@/components/WorkspaceSwitcher'

export function AppShell() {
  return (
    <div className="flex min-h-svh flex-col bg-background text-foreground">
      <header className="border-b">
        <div className="flex h-14 items-center gap-4 px-4">
          <Link to="/" className="flex items-center gap-2 font-heading font-semibold">
            <MessagesSquareIcon className="size-5 text-primary" aria-hidden />
            DocQA
          </Link>
          <div className="h-6 w-px bg-border" aria-hidden />
          <WorkspaceSwitcher />
        </div>
      </header>
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}
