import { type SubmitEvent, useState } from 'react'
import { toast } from 'sonner'

import { useRenameWorkspace } from '@/api/queries'
import type { Workspace } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { MAX_WORKSPACE_NAME_LENGTH } from '@/lib/workspace'

interface RenameWorkspaceDialogProps {
  workspace: Workspace
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function RenameWorkspaceDialog({
  workspace,
  open,
  onOpenChange,
}: RenameWorkspaceDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* Unmounted while closed, so every opening starts from the current name */}
        <RenameForm
          workspace={workspace}
          onDone={() => {
            onOpenChange(false)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function RenameForm({ workspace, onDone }: { workspace: Workspace; onDone: () => void }) {
  const [name, setName] = useState(workspace.name)
  const rename = useRenameWorkspace(workspace.id)
  const trimmed = name.trim()

  function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!trimmed || rename.isPending) return
    if (trimmed === workspace.name) {
      onDone()
      return
    }
    rename.mutate(trimmed, {
      onSuccess: () => {
        toast.success(`Renamed to ${trimmed}`)
        onDone()
      },
    })
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>Rename workspace</DialogTitle>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="rename-workspace-name">Name</Label>
        <Input
          id="rename-workspace-name"
          value={name}
          onChange={(event) => {
            setName(event.target.value)
          }}
          maxLength={MAX_WORKSPACE_NAME_LENGTH}
          autoFocus
          aria-invalid={rename.isError}
          aria-describedby={rename.isError ? 'rename-workspace-error' : undefined}
        />
        {rename.isError && (
          <p id="rename-workspace-error" role="alert" className="text-sm text-destructive">
            {rename.error.message}
          </p>
        )}
      </div>
      <DialogFooter>
        <Button type="submit" disabled={!trimmed || rename.isPending}>
          {rename.isPending ? 'Saving…' : 'Save'}
        </Button>
      </DialogFooter>
    </form>
  )
}
