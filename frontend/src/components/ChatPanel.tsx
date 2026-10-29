import { MessagesSquareIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { ApiError } from '@/api/client'
import { useConfig, useCreateConversation, useDocuments, useMessages } from '@/api/queries'
import { isTurnSaved, useChatStream } from '@/api/useChatStream'
import { AssistantMessage, UserMessage } from '@/components/ChatMessages'
import { CitationPreviewProvider } from '@/components/CitationPreview'
import { Composer } from '@/components/Composer'
import { ConversationList } from '@/components/ConversationList'
import { Button } from '@/components/ui/button'
import { useAutoScroll } from '@/lib/autoScroll'
import { sendBlockedReason } from '@/lib/chat'

/** The chat area: the workspace's conversations beside the open one's thread and the question
 * box. With no conversation in the URL it is a new chat, created by its first question. */
export function ChatPanel({
  workspaceId,
  starterQuestions = [],
}: {
  workspaceId: string
  /** Suggested first questions, shown as chips in a new chat (only the demo workspace has any) */
  starterQuestions?: string[]
}) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const config = useConfig()
  const documents = useDocuments(workspaceId)
  const messages = useMessages(workspaceId, conversationId)
  const create = useCreateConversation(workspaceId)
  const { turn, ask, stop } = useChatStream(workspaceId, conversationId)
  const [draft, setDraft] = useState('')
  const [sendError, setSendError] = useState<string>()

  const saved = messages.data ?? []
  const streaming = turn?.status === 'streaming'
  const blockedReason = sendBlockedReason(documents.data)
  // The question asked here, until the saved messages include it (see isTurnSaved)
  const visibleTurn =
    turn && turn.conversationId === conversationId && !isTurnSaved(turn, saved) ? turn : null

  const threadRef = useRef<HTMLDivElement>(null)
  const { onScroll, stickToBottom } = useAutoScroll(threadRef, [
    conversationId,
    saved.length,
    visibleTurn?.answer,
    visibleTurn?.status,
  ])
  useEffect(stickToBottom, [conversationId, stickToBottom])

  async function send(question: string) {
    setDraft('')
    setSendError(undefined)
    stickToBottom()
    let id = conversationId
    if (!id) {
      try {
        id = (await create.mutateAsync()).id
      } catch (error) {
        setDraft(question)
        setSendError(error instanceof Error ? error.message : 'Could not start a conversation.')
        return
      }
      void navigate(`/w/${workspaceId}/c/${id}`)
    }
    // A finished turn not yet in the saved list will be once it is refetched
    const unsaved = visibleTurn && visibleTurn.status !== 'error' ? 2 : 0
    const outcome = await ask(id, question, saved.length + unsaved)
    // Stopped before any answer: nothing was saved, so give the question back
    if (outcome === 'dropped') setDraft((current) => current || question)
  }

  let thread
  if (conversationId && messages.isError) {
    const notFound = messages.error instanceof ApiError && messages.error.status === 404
    thread = (
      <div className="m-auto grid max-w-sm justify-items-center gap-3 p-8 text-center">
        <p className="font-medium">
          {notFound ? 'Conversation not found' : 'Couldn’t load this conversation'}
        </p>
        <p className="text-sm text-muted-foreground">
          {notFound ? 'It may have been deleted, or the link is wrong.' : messages.error.message}
        </p>
        {notFound ? (
          <Button variant="outline" asChild>
            <Link to={`/w/${workspaceId}`}>Start a new chat</Link>
          </Button>
        ) : (
          <Button variant="outline" onClick={() => void messages.refetch()}>
            Try again
          </Button>
        )}
      </div>
    )
  } else if (conversationId && messages.isPending) {
    thread = <p className="m-auto p-8 text-sm text-muted-foreground">Loading conversation…</p>
  } else if (saved.length === 0 && !visibleTurn) {
    thread = (
      <div className="m-auto grid max-w-sm justify-items-center gap-2 p-8 text-center">
        <MessagesSquareIcon className="size-8 text-muted-foreground" aria-hidden />
        <p className="font-medium">Ask about your documents</p>
        <p className="text-sm text-muted-foreground">
          Answers come only from the files in this workspace, with a source for every claim.
        </p>
        {starterQuestions.length > 0 && (
          <ul aria-label="Suggested questions" className="mt-3 flex flex-wrap justify-center gap-2">
            {starterQuestions.map((question) => (
              <li key={question}>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-auto rounded-full py-1.5 text-left whitespace-normal"
                  disabled={streaming || blockedReason !== undefined}
                  onClick={() => void send(question)}
                >
                  {question}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  } else {
    thread = (
      <ol aria-label="Messages" className="mx-auto grid w-full max-w-3xl grid-cols-1 gap-5 p-4">
        {saved.map((message) => (
          <li key={message.id}>
            {message.role === 'user' ? (
              <UserMessage content={message.content} />
            ) : (
              <AssistantMessage
                content={message.content}
                citations={message.citations}
                refused={message.refused}
                uncited={message.uncited}
                incomplete={message.incomplete}
              />
            )}
          </li>
        ))}
        {visibleTurn && (
          <>
            <li>
              <UserMessage content={visibleTurn.question} />
            </li>
            <li aria-live="polite">
              <AssistantMessage
                content={visibleTurn.answer}
                citations={
                  visibleTurn.status === 'done' ? visibleTurn.citations : visibleTurn.sources
                }
                refused={visibleTurn.refused}
                uncited={visibleTurn.uncited}
                incomplete={visibleTurn.status === 'stopped'}
                streaming={visibleTurn.status === 'streaming'}
                error={visibleTurn.error}
                onRetry={() => {
                  stickToBottom()
                  void ask(visibleTurn.conversationId, visibleTurn.question, saved.length)
                }}
              />
            </li>
          </>
        )}
      </ol>
    )
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
      <div className="max-h-48 shrink-0 overflow-y-auto border-b p-3 lg:max-h-none lg:w-60 lg:border-r lg:border-b-0">
        <ConversationList
          workspaceId={workspaceId}
          busyId={streaming ? turn.conversationId : undefined}
        />
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div ref={threadRef} onScroll={onScroll} className="flex flex-1 flex-col overflow-y-auto">
          <CitationPreviewProvider workspaceId={workspaceId}>{thread}</CitationPreviewProvider>
        </div>
        <div className="mx-auto grid w-full max-w-3xl gap-2 px-4 pt-1 pb-4">
          {sendError && (
            <p role="alert" className="text-sm text-destructive">
              {sendError}
            </p>
          )}
          <Composer
            value={draft}
            onChange={setDraft}
            onSend={(question) => void send(question)}
            onStop={stop}
            streaming={streaming}
            blockedReason={blockedReason}
            maxChars={config.data?.max_question_chars}
          />
        </div>
      </div>
    </div>
  )
}
