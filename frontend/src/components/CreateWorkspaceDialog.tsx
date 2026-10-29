import { type SubmitEvent, useState } from 'react'
import { useNavigate } from 'react-router'

import { useCreateWorkspace } from '@/api/queries'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

// Same limit as the backend's WorkspaceCreate
const MAX_NAME_LENGTH = 100

interface CreateWorkspaceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateWorkspaceDialog({ open, onOpenChange }: CreateWorkspaceDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* Unmounted while closed, so every opening starts with an empty form */}
        <CreateWorkspaceForm
          onCreated={() => {
            onOpenChange(false)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function CreateWorkspaceForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const createWorkspace = useCreateWorkspace()
  const navigate = useNavigate()
  const trimmed = name.trim()

  function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!trimmed || createWorkspace.isPending) return
    createWorkspace.mutate(trimmed, {
      onSuccess: (workspace) => {
        onCreated()
        void navigate(`/w/${workspace.id}`)
      },
    })
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>New workspace</DialogTitle>
        <DialogDescription>
          A workspace holds one business&apos;s documents and conversations.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="workspace-name">Name</Label>
        <Input
          id="workspace-name"
          value={name}
          onChange={(event) => {
            setName(event.target.value)
          }}
          placeholder="Acme Dental"
          maxLength={MAX_NAME_LENGTH}
          autoFocus
          aria-invalid={createWorkspace.isError}
          aria-describedby={createWorkspace.isError ? 'workspace-name-error' : undefined}
        />
        {createWorkspace.isError && (
          <p id="workspace-name-error" role="alert" className="text-sm text-destructive">
            {createWorkspace.error.message}
          </p>
        )}
      </div>
      <DialogFooter>
        <Button type="submit" disabled={!trimmed || createWorkspace.isPending}>
          {createWorkspace.isPending ? 'Creating…' : 'Create workspace'}
        </Button>
      </DialogFooter>
    </form>
  )
}
