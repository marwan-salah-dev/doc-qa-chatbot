import { ClockIcon, LockIcon, PencilIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { useDeleteWorkspace } from '@/api/queries'
import type { Workspace } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { RenameWorkspaceDialog } from '@/components/RenameWorkspaceDialog'
import { Button } from '@/components/ui/button'

/** "Deleted in about 5 h" for a temporary workspace on the public demo. */
function expiryText(expiresAt: string): string {
  const hours = (new Date(expiresAt).getTime() - Date.now()) / 3_600_000
  return hours < 1 ? 'Deleted within the hour' : `Deleted in about ${String(Math.round(hours))} h`
}

/** The workspace's name with rename and delete. Deleting leaves the workspace's page.
 * `readOnly` (the public demo's seeded workspace) swaps the actions for a badge. */
export function WorkspaceHeader({
  workspace,
  readOnly = false,
}: {
  workspace: Workspace
  readOnly?: boolean
}) {
  const navigate = useNavigate()
  const deleteWorkspace = useDeleteWorkspace(workspace.id)
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    try {
      // mutateAsync, not mutate's callbacks: removing the workspace from the cache unmounts this
      // component, and callbacks passed to mutate() don't run once it has unmounted.
      await deleteWorkspace.mutateAsync()
      toast.success(`Deleted ${workspace.name}`)
      void navigate('/')
    } catch {
      // The error is shown in the dialog
    }
  }

  return (
    <div className="grid gap-1.5">
      <div className="flex items-center gap-0.5">
        <h1
          className="min-w-0 flex-1 truncate font-heading text-[0.9375rem] font-semibold"
          title={workspace.name}
        >
          {workspace.name}
        </h1>
        {readOnly ? (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-primary-soft px-1.5 py-0.5 text-[0.6875rem] font-medium text-primary">
            <LockIcon className="size-3" aria-hidden />
            Read-only demo
          </span>
        ) : (
          <>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Rename workspace"
              title="Rename workspace"
              onClick={() => {
                setRenaming(true)
              }}
            >
              <PencilIcon />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Delete workspace"
              title="Delete workspace"
              onClick={() => {
                deleteWorkspace.reset()
                setDeleting(true)
              }}
            >
              <Trash2Icon />
            </Button>
          </>
        )}
      </div>
      {workspace.expires_at && (
        <p
          className="flex items-center gap-1 text-xs text-muted-foreground"
          title={`A temporary demo workspace, deleted at ${new Date(workspace.expires_at).toLocaleString()}`}
        >
          <ClockIcon className="size-3" aria-hidden />
          {expiryText(workspace.expires_at)}
        </p>
      )}

      <RenameWorkspaceDialog workspace={workspace} open={renaming} onOpenChange={setRenaming} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${workspace.name}?`}
        description="All of its documents and conversations are permanently removed."
        pending={deleteWorkspace.isPending}
        error={deleteWorkspace.isError ? deleteWorkspace.error.message : undefined}
        onConfirm={() => void handleDelete()}
      />
    </div>
  )
}
