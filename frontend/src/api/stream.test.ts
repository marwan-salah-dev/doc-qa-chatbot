import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from './client'
import type { ChatStreamEvent } from './sse'
import { streamMessage } from './stream'

const encoder = new TextEncoder()

function streamOf(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk)
      controller.close()
    },
  })
}

function mockFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function collect(): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = []
  await streamMessage({
    workspaceId: 'w1',
    conversationId: 'c1',
    question: 'When are you open?',
    onEvent: (event) => events.push(event),
  })
  return events
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('streamMessage', () => {
  it('delivers sources, deltas and done in order, across byte chunks', async () => {
    const body = encoder.encode(
      'event: sources\ndata: {"sources":[]}\n\n' +
        ': ping\n\n' +
        'event: delta\ndata: {"text":"Café "}\n\n' +
        'event: delta\ndata: {"text":"opens at 9"}\n\n' +
        'event: done\ndata: {"user_message_id":"u1","message_id":"m1","citations":[],' +
        '"refused":false,"uncited":true}\n\n',
    )
    // Split inside the two-byte "é", so the decoder must carry bytes between chunks
    const split = body.indexOf(0xc3) + 1
    const fetchMock = mockFetch(
      new Response(streamOf([body.slice(0, 7), body.slice(7, split), body.slice(split)]), {
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    )

    expect(await collect()).toEqual([
      { type: 'sources', sources: [] },
      { type: 'delta', text: 'Café ' },
      { type: 'delta', text: 'opens at 9' },
      {
        type: 'done',
        user_message_id: 'u1',
        message_id: 'm1',
        citations: [],
        refused: false,
        uncited: true,
      },
    ])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workspaces/w1/conversations/c1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ question: 'When are you open?' }),
      }),
    )
  })

  it('rejects with ApiError when the reply cannot start (409)', async () => {
    mockFetch(
      Response.json(
        { detail: 'A reply is already being written in this conversation.' },
        { status: 409 },
      ),
    )

    const error = await collect().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      message: 'A reply is already being written in this conversation.',
    })
  })

  it('rejects when the stream ends without done or error', async () => {
    mockFetch(new Response(streamOf([encoder.encode('event: delta\ndata: {"text":"Hal')])))

    await expect(collect()).rejects.toThrow(/ended/i)
  })

  it('resolves quietly when aborted', async () => {
    const controller = new AbortController()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        // Behave like fetch: reject with an AbortError once the signal fires
        return new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'))
          })
        })
      }),
    )

    const pending = streamMessage({
      workspaceId: 'w1',
      conversationId: 'c1',
      question: 'Hi',
      signal: controller.signal,
      onEvent: () => undefined,
    })
    controller.abort()
    await expect(pending).resolves.toBeUndefined()
  })
})
