import { FolderPlusIcon } from 'lucide-react'
import { useState } from 'react'
import { Navigate } from 'react-router'

import { useWorkspaces } from '@/api/queries'
import { CreateWorkspaceDialog } from '@/components/CreateWorkspaceDialog'
import { CenteredMessage } from '@/components/CenteredMessage'
import { Button } from '@/components/ui/button'

/** Opens the first workspace, or invites the user to create one. */
export function HomePage() {
  const workspaces = useWorkspaces()
  const [creating, setCreating] = useState(false)

  if (workspaces.isPending) return <CenteredMessage title="Loading workspaces…" />
  if (workspaces.isError) {
    return (
      <CenteredMessage title="Couldn't load workspaces" description={workspaces.error.message} />
    )
  }

  const first = workspaces.data[0]
  if (first) return <Navigate to={`/w/${first.id}`} replace />

  return (
    <CenteredMessage
      icon={<FolderPlusIcon className="size-8 text-muted-foreground" aria-hidden />}
      title="Create your first workspace"
      description="Upload your business documents to a workspace, then ask questions about them."
    >
      <Button
        onClick={() => {
          setCreating(true)
        }}
      >
        New workspace
      </Button>
      <CreateWorkspaceDialog open={creating} onOpenChange={setCreating} />
    </CenteredMessage>
  )
}
