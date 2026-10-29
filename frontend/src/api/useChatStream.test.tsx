// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { makeCitation, makeMessage } from '@/test/render'

import { ApiError } from './client'
import { queryKeys } from './queries'
import type { StreamMessageOptions } from './stream'
import { isTurnSaved, type PendingTurn, useChatStream } from './useChatStream'

const mocks = vi.hoisted(() => ({ stream: vi.fn() }))

vi.mock('./stream', () => ({ streamMessage: mocks.stream }))

const citation = makeCitation()

function setup(conversationId: string | undefined = 'c1') {
  const queryClient = new QueryClient()
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const view = renderHook(({ id }) => useChatStream('ws1', id), {
    wrapper,
    initialProps: { id: conversationId },
  })
  return { ...view, invalidate }
}

/** A stream that sends `text` as one delta, then waits until it is aborted. */
function streamUntilAborted(text: string) {
  mocks.stream.mockImplementation(({ onEvent, signal }: StreamMessageOptions) => {
    if (text) onEvent({ type: 'delta', text })
    return new Promise<void>((resolve) => {
      signal?.addEventListener('abort', () => {
        resolve()
      })
    })
  })
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('useChatStream', () => {
  it('builds the answer from deltas and finishes with the done flags', async () => {
    mocks.stream.mockImplementation(({ onEvent }: StreamMessageOptions) => {
      onEvent({ type: 'sources', sources: [citation, makeCitation({ number: 2 })] })
      onEvent({ type: 'delta', text: 'Open 9 to 5 ' })
      onEvent({ type: 'delta', text: '[1].' })
      onEvent({
        type: 'done',
        user_message_id: 'u1',
        message_id: 'm1',
        citations: [citation],
        refused: false,
        uncited: false,
      })
      return Promise.resolve()
    })
    const { result, invalidate } = setup()

    let outcome: string | undefined
    await act(async () => {
      outcome = await result.current.ask('c1', 'When are you open?', 0)
    })

    expect(outcome).toBe('done')
    expect(result.current.turn).toMatchObject({
      conversationId: 'c1',
      question: 'When are you open?',
      answer: 'Open 9 to 5 [1].',
      status: 'done',
      messageId: 'm1',
      citations: [citation],
    })
    expect(mocks.stream).toHaveBeenCalledWith(
      expect.objectContaining({ workspaceId: 'ws1', conversationId: 'c1' }),
    )
    // The saved messages and the conversation's new title are fetched again
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.messages('ws1', 'c1') })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.conversations('ws1') })
  })

  it('shows the answer while it is still streaming', async () => {
    streamUntilAborted('Partial answer')
    const { result } = setup()

    act(() => {
      void result.current.ask('c1', 'Q?', 0)
    })

    await waitFor(() => {
      expect(result.current.turn?.answer).toBe('Partial answer')
    })
    expect(result.current.turn?.status).toBe('streaming')
    act(() => {
      result.current.stop()
    })
  })

  it('keeps the message of an error event', async () => {
    mocks.stream.mockImplementation(({ onEvent }: StreamMessageOptions) => {
      onEvent({ type: 'error', message: 'The AI service is busy. Please try again.' })
      return Promise.resolve()
    })
    const { result } = setup()

    await act(async () => {
      await result.current.ask('c1', 'Q?', 0)
    })

    expect(result.current.turn).toMatchObject({
      status: 'error',
      error: 'The AI service is busy. Please try again.',
    })
  })

  it('shows the server message when a reply is already in progress (409)', async () => {
    mocks.stream.mockRejectedValue(
      new ApiError(409, 'A reply is already being written in this conversation.'),
    )
    const { result } = setup()

    let outcome: string | undefined
    await act(async () => {
      outcome = await result.current.ask('c1', 'Q?', 0)
    })

    expect(outcome).toBe('error')
    expect(result.current.turn).toMatchObject({
      status: 'error',
      error: 'A reply is already being written in this conversation.',
    })
  })

  it('turns a dropped connection into an error', async () => {
    mocks.stream.mockRejectedValue(new Error('The reply ended unexpectedly. Please try again.'))
    const { result } = setup()

    await act(async () => {
      await result.current.ask('c1', 'Q?', 0)
    })

    expect(result.current.turn?.error).toBe('The reply ended unexpectedly. Please try again.')
  })

  it('keeps a stopped partial answer, marked as stopped', async () => {
    streamUntilAborted('Partial answer')
    const { result } = setup()

    let pending: Promise<string> | undefined
    act(() => {
      pending = result.current.ask('c1', 'Q?', 0)
    })
    await waitFor(() => {
      expect(result.current.turn?.answer).toBe('Partial answer')
    })
    act(() => {
      result.current.stop()
    })

    await act(async () => {
      expect(await pending).toBe('stopped')
    })
    expect(result.current.turn).toMatchObject({ answer: 'Partial answer', status: 'stopped' })
  })

  it('drops the turn when stopped before any text arrived', async () => {
    streamUntilAborted('')
    const { result } = setup()

    let pending: Promise<string> | undefined
    act(() => {
      pending = result.current.ask('c1', 'Q?', 0)
    })
    act(() => {
      result.current.stop()
    })

    await act(async () => {
      expect(await pending).toBe('dropped')
    })
    expect(result.current.turn).toBeNull()
  })

  it('stops the reply when the user leaves its conversation', async () => {
    streamUntilAborted('Partial')
    const { result, rerender } = setup('c1')

    act(() => {
      void result.current.ask('c1', 'Q?', 0)
    })
    await waitFor(() => {
      expect(result.current.turn?.answer).toBe('Partial')
    })
    rerender({ id: 'c2' })

    const { signal } = mocks.stream.mock.calls[0]?.[0] as StreamMessageOptions
    expect(signal?.aborted).toBe(true)
  })

  it('keeps streaming when a new conversation gets its id', () => {
    streamUntilAborted('Partial')
    // The first question of a new chat: the page has no conversation id until it navigates
    const { result, rerender } = setup(undefined)

    act(() => {
      void result.current.ask('c9', 'Q?', 0)
    })
    rerender({ id: 'c9' })

    const { signal } = mocks.stream.mock.calls[0]?.[0] as StreamMessageOptions
    expect(signal?.aborted).toBe(false)
    act(() => {
      result.current.stop()
    })
  })
})

describe('isTurnSaved', () => {
  const turn: PendingTurn = {
    conversationId: 'c1',
    question: 'Q?',
    answer: 'A',
    sources: [],
    citations: [],
    refused: false,
    uncited: false,
    status: 'done',
    baseCount: 2,
  }

  it('is saved once the saved messages include its answer', () => {
    const saved = [makeMessage({ id: 'old' }), makeMessage({ id: 'm1' })]
    expect(isTurnSaved({ ...turn, messageId: 'm1' }, saved)).toBe(true)
    expect(isTurnSaved({ ...turn, messageId: 'm2' }, saved)).toBe(false)
  })

  it('counts a stopped answer as saved once the question and answer are there', () => {
    const stopped = { ...turn, status: 'stopped' as const }
    expect(isTurnSaved(stopped, [makeMessage(), makeMessage()])).toBe(false)
    expect(
      isTurnSaved(
        stopped,
        Array.from({ length: 4 }, () => makeMessage()),
      ),
    ).toBe(true)
  })

  it('never counts a streaming or failed turn as saved', () => {
    const many = Array.from({ length: 6 }, () => makeMessage())
    expect(isTurnSaved({ ...turn, status: 'streaming' }, many)).toBe(false)
    expect(isTurnSaved({ ...turn, status: 'error' }, many)).toBe(false)
  })
})
