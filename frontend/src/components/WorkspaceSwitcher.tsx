import { PlusIcon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { useWorkspaces } from '@/api/queries'
import { CreateWorkspaceDialog } from '@/components/CreateWorkspaceDialog'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/** Picks the current workspace (kept in the URL), with a button to create a new one.
 *
 * "New workspace" is a separate button rather than an item in the list: opening a dialog while
 * the Select is still closing makes the two fight over focus and leaves the list open.
 */
export function WorkspaceSwitcher() {
  const { workspaceId } = useParams()
  const navigate = useNavigate()
  const workspaces = useWorkspaces()
  const [creating, setCreating] = useState(false)
  const hasWorkspaces = Boolean(workspaces.data?.length)

  return (
    <div className="flex min-w-0 items-center gap-2">
      {hasWorkspaces && (
        <Select
          value={workspaceId ?? ''}
          onValueChange={(value) => {
            void navigate(`/w/${value}`)
          }}
        >
          <SelectTrigger className="w-56 min-w-0" aria-label="Workspace">
            <SelectValue placeholder="Select a workspace" />
          </SelectTrigger>
          <SelectContent position="popper" align="start">
            {workspaces.data?.map((workspace) => (
              <SelectItem key={workspace.id} value={workspace.id}>
                {workspace.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      <Button
        variant="outline"
        size={hasWorkspaces ? 'icon' : 'default'}
        disabled={workspaces.isPending}
        aria-label="New workspace"
        title="New workspace"
        onClick={() => {
          setCreating(true)
        }}
      >
        <PlusIcon />
        {!hasWorkspaces && 'New workspace'}
      </Button>
      <CreateWorkspaceDialog open={creating} onOpenChange={setCreating} />
    </div>
  )
}
