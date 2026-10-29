import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { queryKeys } from './queries'
import type { ChatStreamEvent } from './sse'
import { streamMessage } from './stream'
import type { Citation, Message } from './types'

export type TurnStatus = 'streaming' | 'done' | 'stopped' | 'error'

/** How `ask` ended. `dropped` means it was stopped before any answer text arrived, so the
 * backend saved nothing and the turn is gone. */
export type TurnOutcome = TurnStatus | 'dropped'

/** The question being answered (or just answered) in this browser, shown until the saved
 * messages include it. */
export interface PendingTurn {
  conversationId: string
  question: string
  answer: string
  /** Every source given to the model, so `[n]` markers work while the answer streams. */
  sources: Citation[]
  /** Only the sources the finished answer cites. */
  citations: Citation[]
  refused: boolean
  uncited: boolean
  status: TurnStatus
  /** A message safe to show, when `status` is "error". */
  error?: string
  /** The saved answer's id, from the `done` event. */
  messageId?: string
  /** How many saved messages the conversation had before this question. */
  baseCount: number
}

/** Whether the saved messages already include this turn, so the local copy can be hidden.
 * Errors save nothing, and a streaming turn isn't saved yet. A stopped answer has no id, but
 * the backend saves it with its question: two more messages than before. */
export function isTurnSaved(turn: PendingTurn, saved: Message[]): boolean {
  if (turn.status === 'done' && turn.messageId) {
    return saved.some((message) => message.id === turn.messageId)
  }
  if (turn.status === 'stopped') return saved.length >= turn.baseCount + 2
  return false
}

function applyEvent(turn: PendingTurn, event: ChatStreamEvent): PendingTurn {
  switch (event.type) {
    case 'sources':
      return { ...turn, sources: event.sources }
    case 'delta':
      return { ...turn, answer: turn.answer + event.text }
    case 'done':
      return {
        ...turn,
        status: 'done',
        citations: event.citations,
        refused: event.refused,
        uncited: event.uncited,
        messageId: event.message_id,
      }
    case 'error':
      return { ...turn, status: 'error', error: event.message }
  }
}

function errorMessage(error: unknown): string {
  // ApiError and the stream client's own errors carry messages written for users
  return error instanceof Error && error.message
    ? error.message
    : 'Something went wrong. Please try again.'
}

/** Asks questions and streams their replies, one at a time. Leaving the conversation that is
 * streaming (or the page) stops its reply; the backend saves what had arrived as incomplete. */
export function useChatStream(workspaceId: string, activeConversationId: string | undefined) {
  const queryClient = useQueryClient()
  const [turn, setTurn] = useState<PendingTurn | null>(null)
  const controller = useRef<{ conversationId: string; abort: AbortController } | null>(null)

  const stop = useCallback(() => {
    controller.current?.abort.abort()
  }, [])

  // Runs its cleanup when the open conversation changes or the page unmounts. A brand-new
  // conversation streams under its new id before the URL has it, so only the conversation
  // being left is stopped.
  useEffect(() => {
    return () => {
      if (controller.current?.conversationId === activeConversationId) stop()
    }
  }, [activeConversationId, stop])

  const ask = useCallback(
    async (conversationId: string, question: string, baseCount: number): Promise<TurnOutcome> => {
      controller.current?.abort.abort()
      const abort = new AbortController()
      controller.current = { conversationId, abort }
      setTurn({
        conversationId,
        question,
        answer: '',
        sources: [],
        citations: [],
        refused: false,
        uncited: false,
        status: 'streaming',
        baseCount,
      })

      // Widened on purpose: the event callback sets these, which TypeScript can't follow
      let outcome = 'streaming' as TurnOutcome
      let answered = false as boolean
      // A newer question may have replaced this turn; never write over it. Checked now, not
      // inside the state updater, which React may run after this stream has finished.
      const isCurrent = () => controller.current?.abort === abort
      const update = (change: (turn: PendingTurn) => PendingTurn) => {
        if (isCurrent()) setTurn((current) => current && change(current))
      }
      try {
        await streamMessage({
          workspaceId,
          conversationId,
          question,
          signal: abort.signal,
          onEvent: (event) => {
            if (event.type === 'delta') answered = true
            if (event.type === 'done') outcome = 'done'
            if (event.type === 'error') outcome = 'error'
            update((current) => applyEvent(current, event))
          },
        })
        if (abort.signal.aborted) {
          outcome = answered ? 'stopped' : 'dropped'
          if (answered) update((current) => ({ ...current, status: 'stopped' }))
          else if (isCurrent()) setTurn(null)
        }
      } catch (error) {
        outcome = 'error'
        update((current) => ({ ...current, status: 'error', error: errorMessage(error) }))
      }
      if (isCurrent()) controller.current = null

      if (outcome === 'done' || outcome === 'stopped') {
        // The title comes from the first question, so the list may have changed too
        void queryClient.invalidateQueries({
          queryKey: queryKeys.messages(workspaceId, conversationId),
        })
        void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(workspaceId) })
      }
      return outcome
    },
    [queryClient, workspaceId],
  )

  return { turn, ask, stop }
}
