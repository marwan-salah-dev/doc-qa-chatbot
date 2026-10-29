import { ArrowUpRightIcon, FilesIcon, MessagesSquareIcon, PlusIcon } from 'lucide-react'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { ApiError } from '@/api/client'
import { useConfig, useCreateConversation, useDocuments, useMessages } from '@/api/queries'
import { isTurnSaved, useChatStream } from '@/api/useChatStream'
import { AssistantMessage, UserMessage } from '@/components/ChatMessages'
import { CitationPreviewProvider } from '@/components/CitationPreview'
import { Composer } from '@/components/Composer'
import { ConversationList } from '@/components/ConversationList'
import { DocumentUploader } from '@/components/DocumentUploader'
import { LogoMark } from '@/components/LogoMark'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { useAutoScroll } from '@/lib/autoScroll'
import { sendBlockedReason } from '@/lib/chat'
import { useMediaQuery, WIDE_LAYOUT } from '@/lib/useMediaQuery'

/** The chat area: the workspace's conversations beside the open one's thread and the question
 * box. With no conversation in the URL it is a new chat, created by its first question. On
 * narrow screens the conversations (and the documents, when given) open in sheets instead. */
export function ChatPanel({
  workspaceId,
  starterQuestions = [],
  documentsPanel,
}: {
  workspaceId: string
  /** Suggested first questions, shown as cards in a new chat (only the demo workspace has any) */
  starterQuestions?: string[]
  /** On narrow screens, the documents sidebar, opened from the toolbar in a sheet */
  documentsPanel?: ReactNode
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
  const [chatsOpen, setChatsOpen] = useState(false)
  const wide = useMediaQuery(WIDE_LAYOUT)

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
        <MessagesSquareIcon className="size-6 text-muted-foreground" aria-hidden />
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
    thread = (
      <div
        className="mx-auto grid w-full max-w-3xl gap-8 px-4 py-8"
        aria-busy="true"
        aria-label="Loading conversation"
      >
        <Skeleton className="ml-auto h-9 w-2/5 rounded-2xl" />
        <div className="grid gap-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-3/5" />
        </div>
      </div>
    )
  } else if (saved.length === 0 && !visibleTurn && documents.data?.length === 0) {
    thread = <NoDocuments workspaceId={workspaceId} />
  } else if (saved.length === 0 && !visibleTurn) {
    thread = (
      <div className="m-auto grid w-full max-w-2xl justify-items-center gap-3 px-4 py-10 text-center">
        <LogoMark className="mb-1 size-10" />
        <h2 className="font-heading text-xl font-semibold">Ask about your documents</h2>
        <p className="max-w-md text-sm text-balance text-muted-foreground">
          Answers come only from the files in this workspace, with a source for every claim.
        </p>
        {starterQuestions.length > 0 && (
          <ul
            aria-label="Suggested questions"
            className="mt-5 grid w-full grid-cols-1 gap-2 text-left sm:grid-cols-2"
          >
            {starterQuestions.map((question) => (
              <li key={question} className="grid">
                <button
                  type="button"
                  className="group flex items-start justify-between gap-3 rounded-xl border bg-background px-3.5 py-3 text-left text-sm shadow-xs transition-colors hover:border-primary/40 hover:bg-primary-soft/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
                  disabled={streaming || blockedReason !== undefined}
                  onClick={() => void send(question)}
                >
                  <span>{question}</span>
                  <ArrowUpRightIcon
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary"
                    aria-hidden
                  />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  } else {
    thread = (
      <ol
        aria-label="Messages"
        className="mx-auto grid w-full max-w-3xl grid-cols-1 gap-7 px-4 pt-6 pb-4"
      >
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

  const conversations = (
    <ConversationList
      workspaceId={workspaceId}
      busyId={streaming ? turn.conversationId : undefined}
      onNavigate={() => {
        setChatsOpen(false)
      }}
    />
  )
  const readyCount = documents.data?.filter((d) => d.status === 'ready').length

  return (
    <div className="flex min-h-0 min-w-0 flex-1">
      {wide && (
        <div className="w-72 shrink-0 overflow-y-auto border-r bg-surface p-3">{conversations}</div>
      )}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!wide && (
          <div className="flex h-11 shrink-0 items-center gap-1 border-b px-2">
            {documentsPanel && (
              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <FilesIcon />
                    Documents
                    {readyCount !== undefined && (
                      <span className="rounded-full bg-muted px-1.5 font-mono text-[0.6875rem] text-muted-foreground">
                        {readyCount}
                      </span>
                    )}
                  </Button>
                </SheetTrigger>
                <SheetContent title="Documents">{documentsPanel}</SheetContent>
              </Sheet>
            )}
            <Sheet open={chatsOpen} onOpenChange={setChatsOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="sm">
                  <MessagesSquareIcon />
                  Chats
                </Button>
              </SheetTrigger>
              <SheetContent title="Chats">{conversations}</SheetContent>
            </Sheet>
            <Button variant="ghost" size="icon-sm" className="ml-auto" asChild>
              <Link to={`/w/${workspaceId}`} aria-label="New chat" title="New chat">
                <PlusIcon />
              </Link>
            </Button>
          </div>
        )}
        <div ref={threadRef} onScroll={onScroll} className="flex flex-1 flex-col overflow-y-auto">
          <CitationPreviewProvider workspaceId={workspaceId}>{thread}</CitationPreviewProvider>
        </div>
        <div className="mx-auto grid w-full max-w-3xl gap-2 px-3 pt-1 pb-3 sm:px-4 sm:pb-4">
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

const STEPS = [
  ['Upload', 'PDF, DOCX or TXT files: handbooks, price lists, FAQs.'],
  ['Ask', 'Questions in plain language, the way a customer would.'],
  ['Check the source', 'Every answer links to the page or lines it came from.'],
] as const

/** A workspace with no documents yet: the chat area becomes the place to add the first ones. */
function NoDocuments({ workspaceId }: { workspaceId: string }) {
  return (
    <div className="m-auto grid w-full max-w-xl gap-6 px-4 py-10">
      <div className="grid justify-items-center gap-2 text-center">
        <h2 className="font-heading text-xl font-semibold">Add documents to get started</h2>
        <p className="max-w-md text-sm text-balance text-muted-foreground">
          DocQA answers questions using only the files in this workspace.
        </p>
      </div>
      <DocumentUploader workspaceId={workspaceId} size="large" />
      <ol aria-label="How it works" className="grid gap-4 sm:grid-cols-3">
        {STEPS.map(([title, text], index) => (
          <li key={title} className="grid content-start gap-1">
            <span className="flex items-center gap-2 text-sm font-medium">
              <span className="grid size-5 place-items-center rounded-full bg-primary-soft font-mono text-[0.6875rem] text-primary-soft-foreground">
                {index + 1}
              </span>
              {title}
            </span>
            <span className="text-xs text-muted-foreground">{text}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
