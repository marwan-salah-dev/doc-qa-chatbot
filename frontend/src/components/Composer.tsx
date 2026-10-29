import { ArrowUpIcon, SquareIcon } from 'lucide-react'
import { type SyntheticEvent, useId } from 'react'

import { Button } from '@/components/ui/button'

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: (question: string) => void
  onStop: () => void
  streaming: boolean
  /** Why nothing can be sent right now (shown under the box), or undefined when it can. */
  blockedReason?: string
  /** The server's limit, from GET /config. */
  maxChars?: number
}

/** The question box. Enter sends and Shift+Enter starts a new line; while a reply streams the
 * Send button becomes Stop, and the next question can already be typed. */
export function Composer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  blockedReason,
  maxChars,
}: ComposerProps) {
  const hintId = useId()
  const question = value.trim()
  const tooLong = maxChars !== undefined && value.length > maxChars
  const hint =
    blockedReason ??
    (tooLong ? `Questions can be up to ${String(maxChars)} characters.` : undefined)
  const canSend = !streaming && !blockedReason && !tooLong && question.length > 0

  function submit(event?: SyntheticEvent) {
    event?.preventDefault()
    if (canSend) onSend(question)
  }

  return (
    <form onSubmit={submit} className="grid gap-1.5">
      <div className="flex items-end gap-2 rounded-2xl border bg-background p-2 shadow-sm transition-shadow focus-within:border-primary/50 focus-within:ring-3 focus-within:ring-ring/15">
        <textarea
          aria-label="Ask a question"
          aria-describedby={hint ? hintId : undefined}
          aria-invalid={tooLong || undefined}
          rows={1}
          placeholder="Ask a question about your documents…"
          value={value}
          onChange={(event) => {
            onChange(event.target.value)
          }}
          onKeyDown={(event) => {
            // isComposing: Enter also confirms an IME composition (e.g. Japanese input)
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              submit()
            }
          }}
          className="field-sizing-content max-h-40 min-h-9 min-w-0 flex-1 resize-none bg-transparent px-2 py-1.5 text-[0.9375rem] outline-none placeholder:text-muted-foreground"
        />
        {streaming ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="rounded-xl"
            aria-label="Stop"
            onClick={onStop}
          >
            <SquareIcon className="fill-current" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            className="rounded-xl"
            aria-label="Send"
            disabled={!canSend}
          >
            <ArrowUpIcon />
          </Button>
        )}
      </div>
      {hint && (
        <p
          id={hintId}
          className={
            tooLong ? 'px-1 text-xs text-destructive' : 'px-1 text-xs text-muted-foreground'
          }
        >
          {hint}
        </p>
      )}
    </form>
  )
}
