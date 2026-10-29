import { Link, useParams } from 'react-router'

import { useWorkspaces } from '@/api/queries'
import { CenteredMessage } from '@/components/CenteredMessage'
import { ChatPanel } from '@/components/ChatPanel'
import { DocumentList } from '@/components/DocumentList'
import { DocumentUploader } from '@/components/DocumentUploader'
import { Button } from '@/components/ui/button'
import { WorkspaceHeader } from '@/components/WorkspaceHeader'

/** The selected workspace: its documents on the left, and the chat beside them. */
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

  return (
    <div className="flex flex-1 flex-col md:flex-row">
      <aside
        aria-label="Documents"
        className="flex shrink-0 flex-col gap-4 border-b p-4 md:sticky md:top-0 md:h-[calc(100svh-3.5rem-1px)] md:w-80 md:overflow-y-auto md:border-r md:border-b-0"
      >
        <WorkspaceHeader workspace={workspace} />
        <DocumentUploader workspaceId={workspace.id} />
        <DocumentList workspaceId={workspace.id} />
      </aside>
      <section aria-label="Chat" className="flex h-[calc(100svh-3.5rem-1px)] min-w-0 flex-1">
        <ChatPanel workspaceId={workspace.id} />
      </section>
    </div>
  )
}
