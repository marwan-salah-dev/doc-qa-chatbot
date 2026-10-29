import type { Citation, ReplyDone } from './types'

/** One Server-Sent Event as it arrived: the event name and its (possibly multi-line) data. */
export interface RawSseEvent {
  event: string
  data: string
}

export interface SseParser {
  /** Feeds decoded text and returns the events it completed (often none). */
  push: (text: string) => RawSseEvent[]
}

/** An incremental parser for the text/event-stream format.
 *
 * Network chunks can end anywhere (mid-line, between the two newlines that end an event), so
 * incomplete input is buffered until it is complete. Follows the HTML spec's rules for line
 * endings (LF, CRLF or CR), comments and multi-line data; `id` and `retry` are not needed here.
 */
export function createSseParser(): SseParser {
  let buffer = ''
  // A chunk that ended in CR: an LF starting the next chunk belongs to the same line ending
  let skipLeadingLf = false
  let eventName = ''
  let dataLines: string[] = []

  function processLine(line: string): RawSseEvent | null {
    if (line === '') {
      // A blank line ends the event; events without data are dropped
      const event =
        dataLines.length > 0 ? { event: eventName || 'message', data: dataLines.join('\n') } : null
      eventName = ''
      dataLines = []
      return event
    }
    if (line.startsWith(':')) return null // a comment, e.g. a keep-alive ping

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'event') eventName = value
    else if (field === 'data') dataLines.push(value)
    return null
  }

  return {
    push(text) {
      if (skipLeadingLf && text.startsWith('\n')) text = text.slice(1)
      skipLeadingLf = false
      buffer += text

      const events: RawSseEvent[] = []
      let lineStart = 0
      for (let i = 0; i < buffer.length; i++) {
        const char = buffer[i]
        if (char !== '\n' && char !== '\r') continue
        const line = buffer.slice(lineStart, i)
        if (char === '\r') {
          if (i + 1 === buffer.length) skipLeadingLf = true
          else if (buffer[i + 1] === '\n') i++
        }
        lineStart = i + 1
        const event = processLine(line)
        if (event) events.push(event)
      }
      buffer = buffer.slice(lineStart)
      return events
    },
  }
}

/** The chat reply stream: `sources`, then `delta`s, then `done` or `error`. */
export type ChatStreamEvent =
  | { type: 'sources'; sources: Citation[] }
  | { type: 'delta'; text: string }
  | ({ type: 'done' } & ReplyDone)
  | { type: 'error'; message: string }

/** Maps a raw event to a typed one; unknown event names give `null`, so new events can be
 * added to the backend without breaking older clients. */
export function toChatEvent(raw: RawSseEvent): ChatStreamEvent | null {
  switch (raw.event) {
    case 'sources':
      return { type: 'sources', ...(JSON.parse(raw.data) as { sources: Citation[] }) }
    case 'delta':
      return { type: 'delta', ...(JSON.parse(raw.data) as { text: string }) }
    case 'done':
      return { type: 'done', ...(JSON.parse(raw.data) as ReplyDone) }
    case 'error':
      return { type: 'error', ...(JSON.parse(raw.data) as { message: string }) }
    default:
      return null
  }
}
