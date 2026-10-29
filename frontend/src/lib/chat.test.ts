import { describe, expect, it } from 'vitest'

import { makeDocument } from '@/test/render'

import { sendBlockedReason } from './chat'

describe('sendBlockedReason', () => {
  it('allows sending once a document is ready', () => {
    const documents = [makeDocument({ status: 'processing' }), makeDocument({ status: 'ready' })]
    expect(sendBlockedReason(documents)).toBeUndefined()
  })

  it('asks for an upload when there are no documents', () => {
    expect(sendBlockedReason([])).toMatch(/Upload a document/)
  })

  it('asks to wait while documents are being indexed', () => {
    expect(sendBlockedReason([makeDocument({ status: 'pending' })])).toMatch(/being indexed/)
  })

  it('explains when every document failed', () => {
    expect(sendBlockedReason([makeDocument({ status: 'failed' })])).toMatch(/could not be indexed/)
  })

  it('waits for the documents to load', () => {
    expect(sendBlockedReason(undefined)).toMatch(/Loading/)
  })
})
