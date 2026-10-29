import type { Citation } from '@/api/types'
import { CitationPreview } from '@/components/CitationPreview'
import { FileTypeIcon } from '@/components/FileTypeIcon'
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
            'cursor-pointer transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            inline
              ? 'mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded-[0.3rem] bg-primary-soft px-1 align-[0.12em] font-mono text-[0.6875rem] leading-none font-medium text-primary-soft-foreground hover:bg-primary hover:text-primary-foreground'
              : 'inline-flex max-w-full items-center gap-2 rounded-lg border bg-background py-1 pr-2.5 pl-1 text-xs shadow-xs hover:border-primary/40 hover:bg-primary-soft/40',
          )}
        >
          {inline ? (
            citation.number
          ) : (
            <>
              <FileTypeIcon filename={citation.filename} className="size-6 rounded-[0.3rem]" />
              <span className="min-w-0 truncate">
                <span className="font-medium">{citation.filename}</span>
                <span className="text-muted-foreground"> · {citation.label}</span>
              </span>
              <span className="font-mono text-[0.6875rem] text-primary-soft-foreground">
                {citation.number}
              </span>
            </>
          )}
        </button>
      </DialogTrigger>
      <CitationPreview citation={citation} />
    </Dialog>
  )
}
