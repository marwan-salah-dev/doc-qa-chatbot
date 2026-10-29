import { FolderOpenIcon, RefreshCwIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useDeleteDocument, useDocuments, useReindexDocument } from '@/api/queries'
import type { DocumentItem } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DocumentStatusBadge } from '@/components/DocumentStatusBadge'
import { FileTypeIcon } from '@/components/FileTypeIcon'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
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
    return (
      <div className="grid gap-1" aria-busy="true" aria-label="Loading documents">
        {[0, 1, 2].map((row) => (
          <div key={row} className="flex items-center gap-3 p-2">
            <Skeleton className="size-8" />
            <div className="grid flex-1 gap-1.5">
              <Skeleton className="h-3.5 w-3/4" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    )
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
      <div className="grid justify-items-center gap-1.5 rounded-lg border border-dashed px-4 py-6 text-center">
        <FolderOpenIcon className="size-5 text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">
          No documents yet. Upload a file to start asking questions about it.
        </p>
      </div>
    )
  }

  return (
    <div className="grid gap-2">
      {reindex.isError && (
        <p role="alert" className="text-sm text-destructive">
          {reindex.error.message}
        </p>
      )}
      <ul className="grid gap-0.5">
        {documents.data.map((document) => {
          const busy = document.status === 'pending' || document.status === 'processing'
          return (
            <li
              key={document.id}
              className="group grid gap-1.5 rounded-lg p-2 transition-colors hover:bg-muted/70"
            >
              <div className="flex items-center gap-3">
                <FileTypeIcon filename={document.filename} />
                <div className="grid min-w-0 flex-1 gap-0.5">
                  <p className="truncate text-sm font-medium" title={document.filename}>
                    {document.filename}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[0.6875rem] text-muted-foreground">
                      {formatBytes(document.size_bytes)}
                    </span>
                    <DocumentStatusBadge status={document.status} />
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Delete ${document.filename}`}
                  // Deleting mid-index could leave the file's chunks behind in the vector store
                  disabled={busy}
                  title={busy ? 'Wait until indexing finishes' : 'Delete'}
                  className="text-muted-foreground opacity-70 group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100"
                  onClick={() => {
                    remove.reset()
                    setTarget(document)
                    setConfirmOpen(true)
                  }}
                >
                  <Trash2Icon />
                </Button>
              </div>
              {document.status === 'failed' && (
                <div className="ml-11 grid gap-1.5">
                  {document.error && <p className="text-xs text-destructive">{document.error}</p>}
                  <Button
                    variant="outline"
                    size="xs"
                    className="justify-self-start"
                    aria-label={`Reindex ${document.filename}`}
                    disabled={reindex.isPending}
                    onClick={() => {
                      reindex.mutate(document.id, {
                        onSuccess: () => {
                          toast.success(`Reindexing ${document.filename}`)
                        },
                      })
                    }}
                  >
                    <RefreshCwIcon />
                    Reindex
                  </Button>
                </div>
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
              toast.success(`Deleted ${target.filename}`)
            },
          })
        }}
      />
    </div>
  )
}
