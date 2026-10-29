import { Link, useParams } from 'react-router'

import { useWorkspaces } from '@/api/queries'
import { CenteredMessage } from '@/components/CenteredMessage'
import { Button } from '@/components/ui/button'

/** The selected workspace. Its documents (step 13) and chat (step 14) go in the main area. */
export function WorkspacePage() {
  const { workspaceId } = useParams()
  const workspaces = useWorkspaces()

  if (workspaces.isPending) return <CenteredMessage title="Loading workspace…" />
  if (workspaces.isError) {
    return (
      <CenteredMessage title="Couldn't load workspaces" description={workspaces.error.message} />
    )
  }

  const workspace = workspaces.data.find((w) => w.id === workspaceId)
  if (!workspace) {
    return (
      <CenteredMessage
        title="Workspace not found"
        description="It may have been deleted, or the link is wrong."
      >
        <Button variant="outline" asChild>
          <Link to="/">Go to your workspaces</Link>
        </Button>
      </CenteredMessage>
    )
  }

  return <section aria-label={workspace.name} className="flex flex-1" />
}
