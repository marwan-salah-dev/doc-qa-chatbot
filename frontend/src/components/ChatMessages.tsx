import { AlertCircleIcon, InfoIcon, RotateCcwIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import type { Citation } from '@/api/types'
import { CitationChip } from '@/components/CitationChip'
import { LogoMark } from '@/components/LogoMark'
import { Markdown } from '@/components/Markdown'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { splitCitations } from '@/lib/citations'

export function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      {/* Questions are shown exactly as typed, not as markdown */}
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary-soft px-4 py-2.5 text-[0.9375rem] leading-relaxed break-words whitespace-pre-wrap">
        {content}
      </p>
    </div>
  )
}

interface AssistantMessageProps {
  content: string
  /** The sources `[n]` markers can point to: while streaming every source, once saved only the
   * cited ones. */
  citations: Citation[]
  refused?: boolean
  uncited?: boolean
  incomplete?: boolean
  streaming?: boolean
  /** Set when the reply failed; nothing was saved, so it can be asked again. */
  error?: string
  onRetry?: () => void
}

/** The agent's side of the thread: its mark beside the reply, with no bubble, like a document. */
function AgentRow({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <LogoMark className="mt-0.5 size-6" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

export function AssistantMessage({
  content,
  citations,
  refused = false,
  uncited = false,
  incomplete = false,
  streaming = false,
  error,
  onRetry,
}: AssistantMessageProps) {
  if (error) {
    return (
      <AgentRow>
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm"
        >
          <AlertCircleIcon className="size-4 shrink-0 text-destructive" aria-hidden />
          <p className="min-w-0 flex-1 text-destructive">{error}</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RotateCcwIcon />
              Retry
            </Button>
          )}
        </div>
      </AgentRow>
    )
  }

  if (refused) {
    // The fixed "not found" reply: shown apart from real answers, so nobody mistakes it for one
    return (
      <AgentRow>
        <div className="grid gap-1 rounded-xl border border-dashed bg-surface px-4 py-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <InfoIcon className="size-3.5" aria-hidden />
            Not found in your documents
          </p>
          <p className="text-sm text-muted-foreground">{content}</p>
        </div>
      </AgentRow>
    )
  }

  // Sources in the order the answer first cites them; while streaming only those cited so far
  const cited = citedInOrder(content, citations)

  return (
    <AgentRow>
      <div className="grid grid-cols-1 gap-3" aria-busy={streaming}>
        {content ? (
          <Markdown text={content} citations={citations} />
        ) : (
          <p className="flex items-center gap-2 py-0.5 text-sm text-muted-foreground">
            <span className="flex gap-1" aria-hidden>
              <span className="size-1.5 animate-bounce rounded-full bg-primary/70 [animation-delay:-0.3s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-primary/70 [animation-delay:-0.15s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-primary/70" />
            </span>
            Searching your documents…
          </p>
        )}
        {(uncited || incomplete) && (
          <div className="flex flex-wrap gap-1.5">
            {uncited && (
              <Badge variant="warning">
                No sources cited. Check this answer before relying on it.
              </Badge>
            )}
            {incomplete && <Badge variant="secondary">Stopped</Badge>}
          </div>
        )}
        {cited.length > 0 && (
          // grid-cols-1 caps the column at the message width, so long chips truncate on a phone
          <div className="grid grid-cols-1 gap-1.5">
            <p className="text-xs font-medium text-muted-foreground">Sources</p>
            <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
              {cited.map((citation) => (
                <li key={citation.number} className="max-w-full min-w-0">
                  <CitationChip citation={citation} variant="source" />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </AgentRow>
  )
}

function citedInOrder(content: string, citations: Citation[]): Citation[] {
  const byNumber = new Map(citations.map((c) => [c.number, c]))
  const numbers = splitCitations(content, new Set(byNumber.keys())).filter(
    (part) => typeof part === 'number',
  )
  return [...new Set(numbers)].map((n) => byNumber.get(n)).filter((c) => c !== undefined)
}
