import type { ReactNode } from 'react'

interface CenteredMessageProps {
  title: string
  description?: string
  icon?: ReactNode
  children?: ReactNode
}

/** A short message in the middle of the main area: loading, empty and error states. */
export function CenteredMessage({ title, description, icon, children }: CenteredMessageProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
      {icon}
      <h1 className="font-heading text-lg font-semibold">{title}</h1>
      {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      {children}
    </div>
  )
}
