import { apiHeaders } from '@/lib/visitor'

import { apiPath, errorFromResponse } from './client'
import { type ChatStreamEvent, createSseParser, toChatEvent } from './sse'

export interface StreamMessageOptions {
  workspaceId: string
  conversationId: string
  question: string
  onEvent: (event: ChatStreamEvent) => void
  /** Aborting stops the reply (the backend saves the partial answer as incomplete). */
  signal?: AbortSignal
}

/** Asks a question and streams the reply.
 *
 * Uses fetch + ReadableStream because EventSource can only send GET requests. Resolves once the
 * stream ends, or quietly when aborted. Rejects with `ApiError` when the reply can't start
 * (404, 409 while another reply is streaming, 422), and with an `Error` if the connection
 * drops before a `done` or `error` event.
 */
export async function streamMessage({
  workspaceId,
  conversationId,
  question,
  onEvent,
  signal,
}: StreamMessageOptions): Promise<void> {
  try {
    const response = await fetch(
      apiPath`/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
      {
        method: 'POST',
        headers: {
          ...apiHeaders(),
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ question }),
        signal,
      },
    )
    if (!response.ok) throw await errorFromResponse(response)
    if (!response.body) throw new Error('The reply could not be started. Please try again.')

    const reader = response.body.getReader()
    // `stream: true` keeps a multi-byte character that is split across chunks intact
    const decoder = new TextDecoder()
    const parser = createSseParser()
    let finished = false

    for (;;) {
      const { done, value } = await reader.read()
      const text = done ? decoder.decode() : decoder.decode(value, { stream: true })
      for (const raw of parser.push(text)) {
        const event = toChatEvent(raw)
        if (!event) continue
        onEvent(event)
        if (event.type === 'done' || event.type === 'error') finished = true
      }
      if (done) break
    }

    if (!finished) throw new Error('The reply ended unexpectedly. Please try again.')
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    throw error
  }
}
