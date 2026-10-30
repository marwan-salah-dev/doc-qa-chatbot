import { Link, useParams } from 'react-router'

import { useConfig, useWorkspaces } from '@/api/queries'
import { CenteredMessage } from '@/components/CenteredMessage'
import { ChatPanel } from '@/components/ChatPanel'
import { DocumentList } from '@/components/DocumentList'
import { DocumentUploader } from '@/components/DocumentUploader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { WorkspaceHeader } from '@/components/WorkspaceHeader'
import { useMediaQuery, WIDE_LAYOUT } from '@/lib/useMediaQuery'

/** The selected workspace: its documents on the left, and the chat beside them. On narrow
 * screens the documents move into a sheet the chat's toolbar opens. */
export function WorkspacePage() {
  const { workspaceId } = useParams()
  const workspaces = useWorkspaces()
  const config = useConfig()
  const wide = useMediaQuery(WIDE_LAYOUT)

  if (workspaces.isPending) {
    return (
      <div className="flex flex-1" aria-busy="true" aria-label="Loading workspace">
        <div className="hidden w-80 gap-4 border-r bg-surface p-4 lg:grid lg:content-start">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
        <div className="m-auto grid w-full max-w-md justify-items-center gap-3 p-8">
          <Skeleton className="size-10 rounded-xl" />
          <Skeleton className="h-5 w-56" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </div>
      </div>
    )
  }
  if (workspaces.isError) {
    return (
      <CenteredMessage title="Couldn't load workspaces" description={workspaces.error.message}>
        <Button variant="outline" onClick={() => void workspaces.refetch()}>
          Try again
        </Button>
      </CenteredMessage>
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

  // The public demo's seeded workspace: the server refuses changes, so don't offer them
  const readOnly = workspace.is_demo && config.data?.public_demo === true
  const documents = (
    <div className="grid content-start gap-5">
      <WorkspaceHeader workspace={workspace} readOnly={readOnly} />
      <section aria-labelledby="documents-heading" className="grid gap-3">
        <h2 id="documents-heading" className="text-xs font-medium text-muted-foreground">
          Documents
        </h2>
        {!readOnly && <DocumentUploader workspaceId={workspace.id} />}
        <DocumentList workspaceId={workspace.id} readOnly={readOnly} />
      </section>
    </div>
  )

  return (
    <div className="flex min-h-0 flex-1">
      {wide && (
        <aside
          aria-label="Documents"
          className="w-72 shrink-0 overflow-y-auto border-r bg-surface p-4 xl:w-80"
        >
          {documents}
        </aside>
      )}
      <section aria-label="Chat" className="flex min-h-0 min-w-0 flex-1">
        <ChatPanel
          workspaceId={workspace.id}
          starterQuestions={workspace.starter_questions}
          documentsPanel={wide ? undefined : documents}
        />
      </section>
    </div>
  )
}
