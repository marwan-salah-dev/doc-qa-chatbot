import { PencilIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { useDeleteWorkspace } from '@/api/queries'
import type { Workspace } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { RenameWorkspaceDialog } from '@/components/RenameWorkspaceDialog'
import { Button } from '@/components/ui/button'

/** The workspace's name with rename and delete. Deleting leaves the workspace's page. */
export function WorkspaceHeader({ workspace }: { workspace: Workspace }) {
  const navigate = useNavigate()
  const deleteWorkspace = useDeleteWorkspace(workspace.id)
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    try {
      // mutateAsync, not mutate's callbacks: removing the workspace from the cache unmounts this
      // component, and callbacks passed to mutate() don't run once it has unmounted.
      await deleteWorkspace.mutateAsync()
      void navigate('/')
    } catch {
      // The error is shown in the dialog
    }
  }

  return (
    <div className="flex items-center gap-1">
      <h1
        className="min-w-0 flex-1 truncate font-heading text-base font-semibold"
        title={workspace.name}
      >
        {workspace.name}
      </h1>
      <Button
        variant="ghost"
        size="icon"
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
        size="icon"
        aria-label="Delete workspace"
        title="Delete workspace"
        onClick={() => {
          deleteWorkspace.reset()
          setDeleting(true)
        }}
      >
        <Trash2Icon />
      </Button>

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
