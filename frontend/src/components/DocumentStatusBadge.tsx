import { CircleAlertIcon, CircleCheckIcon, ClockIcon, LoaderCircleIcon } from 'lucide-react'

import type { DocumentStatus } from '@/api/types'
import { Badge } from '@/components/ui/badge'

const STATUS: Record<
  DocumentStatus,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' }
> = {
  pending: { label: 'Pending', variant: 'secondary' },
  processing: { label: 'Processing', variant: 'warning' },
  ready: { label: 'Ready', variant: 'success' },
  failed: { label: 'Failed', variant: 'destructive' },
}

const ICONS = {
  pending: <ClockIcon aria-hidden />,
  processing: <LoaderCircleIcon className="animate-spin" aria-hidden />,
  ready: <CircleCheckIcon aria-hidden />,
  failed: <CircleAlertIcon aria-hidden />,
} satisfies Record<DocumentStatus, React.ReactNode>

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const { label, variant } = STATUS[status]
  return (
    <Badge variant={variant}>
      {ICONS[status]}
      {label}
    </Badge>
  )
}
