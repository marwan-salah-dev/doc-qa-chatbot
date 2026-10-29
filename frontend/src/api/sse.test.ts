import { describe, expect, it } from 'vitest'

import { createSseParser, toChatEvent } from './sse'

function pushAll(chunks: string[]) {
  const parser = createSseParser()
  return chunks.flatMap((chunk) => parser.push(chunk))
}

describe('createSseParser', () => {
  it('parses one complete event', () => {
    expect(pushAll(['event: delta\ndata: {"text":"Hi"}\n\n'])).toEqual([
      { event: 'delta', data: '{"text":"Hi"}' },
    ])
  })

  it('waits for an event split across chunks and emits it once', () => {
    const parser = createSseParser()
    expect(parser.push('eve')).toEqual([])
    expect(parser.push('nt: delta\nda')).toEqual([])
    expect(parser.push('ta: {"text":"Hel')).toEqual([])
    expect(parser.push('lo"}\n')).toEqual([])
    expect(parser.push('\n')).toEqual([{ event: 'delta', data: '{"text":"Hello"}' }])
  })

  it('parses several events in one chunk', () => {
    expect(pushAll(['event: delta\ndata: a\n\nevent: delta\ndata: b\n\n'])).toEqual([
      { event: 'delta', data: 'a' },
      { event: 'delta', data: 'b' },
    ])
  })

  it('handles CRLF and CR line endings, including CRLF split across chunks', () => {
    expect(pushAll(['event: delta\r\ndata: a\r', '\n\r', '\nevent: done\rdata: b\r\r'])).toEqual([
      { event: 'delta', data: 'a' },
      { event: 'done', data: 'b' },
    ])
  })

  it('joins multi-line data with newlines', () => {
    expect(pushAll(['data: line one\ndata: line two\n\n'])).toEqual([
      { event: 'message', data: 'line one\nline two' },
    ])
  })

  it('removes only one space after the colon', () => {
    expect(pushAll(['data:no space\n\ndata:  two spaces\n\n'])).toEqual([
      { event: 'message', data: 'no space' },
      { event: 'message', data: ' two spaces' },
    ])
  })

  it('ignores comments (keep-alive pings) and events without data', () => {
    expect(pushAll([': ping\n\nevent: delta\n\n: ping\nevent: delta\ndata: x\n\n'])).toEqual([
      { event: 'delta', data: 'x' },
    ])
  })
})

describe('toChatEvent', () => {
  const citation = {
    number: 1,
    document_id: 'd1',
    filename: 'faq.pdf',
    location: { kind: 'pdf', page: 2 },
    label: 'page 2',
    text: 'Opening hours are 9-5.',
    score: 0.8,
  }

  it('maps sources', () => {
    const data = JSON.stringify({ sources: [citation] })
    expect(toChatEvent({ event: 'sources', data })).toEqual({
      type: 'sources',
      sources: [citation],
    })
  })

  it('maps delta', () => {
    expect(toChatEvent({ event: 'delta', data: '{"text":"Hi"}' })).toEqual({
      type: 'delta',
      text: 'Hi',
    })
  })

  it('maps done', () => {
    const payload = {
      user_message_id: 'u1',
      message_id: 'm1',
      citations: [citation],
      refused: false,
      uncited: false,
    }
    expect(toChatEvent({ event: 'done', data: JSON.stringify(payload) })).toEqual({
      type: 'done',
      ...payload,
    })
  })

  it('maps error', () => {
    expect(toChatEvent({ event: 'error', data: '{"message":"Busy"}' })).toEqual({
      type: 'error',
      message: 'Busy',
    })
  })

  it('ignores unknown events', () => {
    expect(toChatEvent({ event: 'something-new', data: '{}' })).toBeNull()
  })
})
