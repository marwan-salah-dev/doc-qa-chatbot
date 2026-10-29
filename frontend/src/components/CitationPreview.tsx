import { useQuery } from '@tanstack/react-query'
import { ExternalLinkIcon } from 'lucide-react'
import { Component, createContext, lazy, type ReactNode, Suspense, useContext } from 'react'

import { api } from '@/api/client'
import type { Citation } from '@/api/types'
import { DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { citedPages, lineWindow } from '@/lib/citationPreview'

const PdfPages = lazy(() => import('@/components/PdfPages'))

/** The workspace whose documents citations point to; without it only the passage is shown. */
const WorkspaceIdContext = createContext<string | null>(null)

export function CitationPreviewProvider({
  workspaceId,
  children,
}: {
  workspaceId: string
  children: ReactNode
}) {
  return <WorkspaceIdContext value={workspaceId}>{children}</WorkspaceIdContext>
}

/** The panel a citation chip opens: the cited passage in its file. Everything except the
 * original file comes from the citation itself (saved with the message, or sent in the stream),
 * so it works the same for live and saved answers. Render inside a `Dialog`. */
export function CitationPreview({ citation }: { citation: Citation }) {
  const workspaceId = useContext(WorkspaceIdContext)
  const fileUrl = workspaceId ? api.documents.fileUrl(workspaceId, citation.document_id) : null
  const { location } = citation
  const passage = <Passage text={citation.text} />

  return (
    // A panel down the right side; on a phone it fills the screen
    <DialogContent className="top-0 right-0 left-auto flex h-dvh w-full max-w-full translate-x-0 translate-y-0 flex-col gap-0 rounded-none p-0 sm:max-w-xl data-open:zoom-in-100 data-open:slide-in-from-right-8 data-closed:zoom-out-100 data-closed:slide-out-to-right-8">
      <DialogHeader className="gap-1 border-b px-4 py-3 pr-12">
        <DialogTitle className="truncate leading-snug">{citation.filename}</DialogTitle>
        <DialogDescription>{citation.label}</DialogDescription>
      </DialogHeader>

      {/* Rows fit their content: in a fixed-height grid, boxes that scroll would be squeezed */}
      <div className="grid min-h-0 flex-1 [scrollbar-gutter:stable] auto-rows-max grid-cols-1 content-start gap-4 overflow-y-auto px-4 py-4">
        {location.kind === 'pdf' && fileUrl && (
          <OriginalFileBoundary>
            <Suspense fallback={<p className="text-sm text-muted-foreground">Loading the PDF…</p>}>
              <PdfPages url={fileUrl} pages={citedPages(location)} passage={citation.text} />
            </Suspense>
          </OriginalFileBoundary>
        )}

        {location.kind === 'docx' && (
          <div className="grid gap-0.5">
            {location.heading && <p className="font-medium">{location.heading}</p>}
            <p className="text-xs text-muted-foreground">{paragraphs(citation)}</p>
          </div>
        )}

        {location.kind === 'txt' && workspaceId ? (
          <TextContext workspaceId={workspaceId} citation={citation} fallback={passage} />
        ) : (
          passage
        )}
      </div>

      {fileUrl && (
        <div className="border-t px-4 py-3">
          <a
            href={fileUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium underline-offset-4 hover:underline"
          >
            <ExternalLinkIcon className="size-4" aria-hidden />
            Open original
          </a>
        </div>
      )}
    </DialogContent>
  )
}

function paragraphs({ location }: Citation): string {
  const { start, end } = location
  if (start == null) return ''
  return end == null || end === start
    ? `Paragraph ${String(start)}`
    : `Paragraphs ${String(start)}–${String(end)}`
}

function Passage({ text }: { text: string }) {
  return (
    <section aria-labelledby="cited-passage" className="grid gap-1.5">
      <h3 id="cited-passage" className="text-xs font-medium text-muted-foreground">
        Cited passage
      </h3>
      <blockquote className="border-l-2 border-primary/60 pl-3 text-sm leading-relaxed whitespace-pre-wrap">
        {text}
      </blockquote>
    </section>
  )
}

/** A TXT passage as the cited lines of the file, numbered and highlighted, with a few lines
 * either side. Shows `fallback` (the passage on its own) when the file can't be used. */
function TextContext({
  workspaceId,
  citation,
  fallback,
}: {
  workspaceId: string
  citation: Citation
  fallback: ReactNode
}) {
  const { start, end } = citation.location
  const file = useQuery({
    queryKey: ['documents', workspaceId, citation.document_id, 'text'],
    queryFn: () => api.documents.fileText(workspaceId, citation.document_id),
    staleTime: Infinity,
  })

  if (file.isPending) return <p className="text-sm text-muted-foreground">Loading the file…</p>
  if (file.isError) {
    return (
      <>
        <FileUnavailable />
        {fallback}
      </>
    )
  }
  const lines = start == null ? [] : lineWindow(file.data, start, end ?? start)
  if (lines.length === 0) return fallback

  return (
    <ol
      aria-label="Lines around the passage"
      className="rounded-md border bg-muted/30 py-1.5 font-mono text-xs leading-relaxed"
    >
      {lines.map((line) => (
        <li
          key={line.number}
          data-cited={line.cited}
          className="flex gap-3 px-2 data-[cited=false]:text-muted-foreground data-[cited=true]:bg-primary/10"
        >
          <span className="w-6 shrink-0 text-right text-muted-foreground select-none">
            {line.number}
          </span>
          <span className="whitespace-pre-wrap">{line.text}</span>
        </li>
      ))}
    </ol>
  )
}

function FileUnavailable() {
  return (
    <p className="text-sm text-muted-foreground">
      Couldn&apos;t load the original file. The cited passage is shown below.
    </p>
  )
}

/** Keeps a failure in the PDF viewer (a missing file, a broken PDF, the viewer's code failing
 * to download) inside the panel: the passage still shows and the rest of the app keeps working. */
class OriginalFileBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  override render() {
    return this.state.failed ? <FileUnavailable /> : this.props.children
  }
}
