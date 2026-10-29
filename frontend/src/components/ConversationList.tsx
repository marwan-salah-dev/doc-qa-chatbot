import { MessageSquareIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useConversations, useDeleteConversation } from '@/api/queries'
import type { Conversation } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** A conversation's title is its first question, empty until one is asked. */
function titleOf(conversation: Conversation): string {
  return conversation.title === '' ? 'New conversation' : conversation.title
}

interface ConversationListProps {
  workspaceId: string
  /** The conversation streaming a reply, which can't be deleted until it finishes. */
  busyId?: string
}

/** The workspace's conversations, newest first. The open one comes from the URL. */
export function ConversationList({ workspaceId, busyId }: ConversationListProps) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const conversations = useConversations(workspaceId)
  const remove = useDeleteConversation(workspaceId)
  // The target outlives the dialog's closing animation, so its title doesn't go blank mid-fade
  const [target, setTarget] = useState<Conversation>()
  const [confirmOpen, setConfirmOpen] = useState(false)

  let list
  if (conversations.isPending) {
    list = <p className="px-2 text-sm text-muted-foreground">Loading conversations…</p>
  } else if (conversations.isError) {
    list = (
      <div className="grid gap-2 px-2 text-sm">
        <p role="alert" className="text-destructive">
          {conversations.error.message}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="justify-self-start"
          onClick={() => void conversations.refetch()}
        >
          Try again
        </Button>
      </div>
    )
  } else if (conversations.data.length === 0) {
    list = (
      <p className="px-2 text-sm text-muted-foreground">
        No conversations yet. Ask a question to start one.
      </p>
    )
  } else {
    list = (
      <ul className="grid grid-cols-1 gap-0.5">
        {conversations.data.map((conversation) => {
          const title = titleOf(conversation)
          const active = conversation.id === conversationId
          const busy = conversation.id === busyId
          return (
            <li
              key={conversation.id}
              className={cn(
                'group flex items-center gap-1 rounded-md pr-1 hover:bg-accent',
                active && 'bg-accent',
              )}
            >
              <Link
                to={`/w/${workspaceId}/c/${conversation.id}`}
                aria-current={active ? 'page' : undefined}
                className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                title={title}
              >
                <MessageSquareIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className={cn('truncate', active && 'font-medium')}>{title}</span>
              </Link>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Delete conversation: ${title}`}
                // The backend is still writing its answer; deleting now would race with that save
                disabled={busy}
                title={busy ? 'Wait until the answer finishes' : 'Delete'}
                className="shrink-0 opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
                onClick={() => {
                  remove.reset()
                  setTarget(conversation)
                  setConfirmOpen(true)
                }}
              >
                <Trash2Icon />
              </Button>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <nav aria-label="Conversations" className="grid grid-cols-1 content-start gap-2">
      <Button variant="outline" size="sm" className="justify-start" asChild>
        <Link to={`/w/${workspaceId}`}>
          <PlusIcon />
          New chat
        </Link>
      </Button>
      {list}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Delete “${target ? titleOf(target) : 'this conversation'}”?`}
        description="The conversation and all of its messages are removed. This can't be undone."
        pending={remove.isPending}
        error={remove.isError ? remove.error.message : undefined}
        onConfirm={() => {
          if (!target) return
          remove.mutate(target.id, {
            onSuccess: () => {
              setConfirmOpen(false)
              if (target.id === conversationId) void navigate(`/w/${workspaceId}`)
            },
          })
        }}
      />
    </nav>
  )
}
