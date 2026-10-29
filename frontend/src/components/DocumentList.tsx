import { FileTextIcon, RefreshCwIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { useDeleteDocument, useDocuments, useReindexDocument } from '@/api/queries'
import type { DocumentItem } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DocumentStatusBadge } from '@/components/DocumentStatusBadge'
import { Button } from '@/components/ui/button'
import { formatBytes } from '@/lib/formatBytes'

/** The workspace's documents with their indexing status. The list refreshes itself while any
 * document is still being indexed (see `documentsRefetchInterval`). */
export function DocumentList({ workspaceId }: { workspaceId: string }) {
  const documents = useDocuments(workspaceId)
  const reindex = useReindexDocument(workspaceId)
  const remove = useDeleteDocument(workspaceId)
  // The target outlives the dialog's closing animation, so its title doesn't go blank mid-fade
  const [target, setTarget] = useState<DocumentItem>()
  const [confirmOpen, setConfirmOpen] = useState(false)

  if (documents.isPending) {
    return <p className="text-sm text-muted-foreground">Loading documents…</p>
  }
  if (documents.isError) {
    return (
      <div className="grid gap-2 text-sm">
        <p role="alert" className="text-destructive">
          {documents.error.message}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="justify-self-start"
          onClick={() => void documents.refetch()}
        >
          Try again
        </Button>
      </div>
    )
  }
  if (documents.data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No documents yet. Upload a file to start asking questions about it.
      </p>
    )
  }

  return (
    <div className="grid gap-2">
      {reindex.isError && (
        <p role="alert" className="text-sm text-destructive">
          {reindex.error.message}
        </p>
      )}
      <ul className="grid gap-2">
        {documents.data.map((document) => {
          const busy = document.status === 'pending' || document.status === 'processing'
          return (
            <li key={document.id} className="grid gap-1.5 rounded-lg border p-2.5">
              <div className="flex items-center gap-2">
                <FileTextIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={document.filename}>
                    {document.filename}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatBytes(document.size_bytes)}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${document.filename}`}
                  // Deleting mid-index could leave the file's chunks behind in the vector store
                  disabled={busy}
                  title={busy ? 'Wait until indexing finishes' : 'Delete'}
                  onClick={() => {
                    remove.reset()
                    setTarget(document)
                    setConfirmOpen(true)
                  }}
                >
                  <Trash2Icon />
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <DocumentStatusBadge status={document.status} />
                {document.status === 'failed' && (
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={`Reindex ${document.filename}`}
                    disabled={reindex.isPending}
                    onClick={() => {
                      reindex.mutate(document.id)
                    }}
                  >
                    <RefreshCwIcon />
                    Reindex
                  </Button>
                )}
              </div>
              {document.status === 'failed' && document.error && (
                <p className="text-xs text-destructive">{document.error}</p>
              )}
            </li>
          )
        })}
      </ul>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Delete ${target?.filename ?? 'this document'}?`}
        description="The file and everything indexed from it are removed. Answers will no longer use it."
        pending={remove.isPending}
        error={remove.isError ? remove.error.message : undefined}
        onConfirm={() => {
          if (!target) return
          remove.mutate(target.id, {
            onSuccess: () => {
              setConfirmOpen(false)
            },
          })
        }}
      />
    </div>
  )
}
