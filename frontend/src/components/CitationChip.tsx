import type { Citation } from '@/api/types'
import { CitationPreview } from '@/components/CitationPreview'
import { Dialog, DialogTrigger } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

interface CitationChipProps {
  citation: Citation
  /** `inline` is the small number inside the answer; `source` the labelled chip below it. */
  variant?: 'inline' | 'source'
}

/** A cited source. Clicking it opens the preview panel with the passage in its file. */
export function CitationChip({ citation, variant = 'inline' }: CitationChipProps) {
  const inline = variant === 'inline'
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label={
            inline
              ? `Source ${String(citation.number)}: ${citation.filename}, ${citation.label}`
              : undefined
          }
          title={inline ? `${citation.filename} · ${citation.label}` : undefined}
          className={cn(
            'cursor-pointer border font-medium transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            inline
              ? 'mx-0.5 inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-md bg-muted px-1 align-[0.15em] text-[0.7rem] leading-none'
              : 'inline-flex max-w-full items-center gap-1.5 rounded-full bg-background px-2.5 py-1 text-xs',
          )}
        >
          {inline ? (
            citation.number
          ) : (
            <>
              <span className="rounded-full bg-muted px-1.5 text-[0.7rem]">{citation.number}</span>
              <span className="truncate">
                {citation.filename} · {citation.label}
              </span>
            </>
          )}
        </button>
      </DialogTrigger>
      <CitationPreview citation={citation} />
    </Dialog>
  )
}
