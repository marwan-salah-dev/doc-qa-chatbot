import type { Citation } from '@/api/types'
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'

interface CitationChipProps {
  citation: Citation
  /** `inline` is the small number inside the answer; `source` the labelled chip below it. */
  variant?: 'inline' | 'source'
}

/** A cited source. Clicking it shows the passage the answer used (step 15 replaces this
 * popover with the full preview panel). */
export function CitationChip({ citation, variant = 'inline' }: CitationChipProps) {
  const inline = variant === 'inline'
  return (
    <Popover>
      <PopoverTrigger asChild>
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
      </PopoverTrigger>
      <PopoverContent className="w-80 max-w-[calc(100vw-2rem)]" align="start">
        <PopoverHeader>
          <PopoverTitle className="truncate">{citation.filename}</PopoverTitle>
          <PopoverDescription>{citation.label}</PopoverDescription>
        </PopoverHeader>
        <blockquote className="max-h-60 overflow-y-auto border-l-2 pl-3 text-xs leading-relaxed whitespace-pre-wrap">
          {citation.text}
        </blockquote>
      </PopoverContent>
    </Popover>
  )
}
