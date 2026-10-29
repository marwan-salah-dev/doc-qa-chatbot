import { describe, expect, it } from 'vitest'

import { documentsRefetchInterval } from './queries'
import type { DocumentItem, DocumentStatus } from './types'

function doc(status: DocumentStatus): DocumentItem {
  return {
    id: status,
    workspace_id: 'w',
    filename: `${status}.txt`,
    content_type: 'text/plain',
    size_bytes: 1,
    sha256: 'a'.repeat(64),
    status,
    error: null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('documentsRefetchInterval', () => {
  it.each<DocumentStatus>(['pending', 'processing'])('polls while a document is %s', (status) => {
    expect(documentsRefetchInterval([doc('ready'), doc(status)])).toBe(2000)
  })

  it('stops once everything has settled', () => {
    expect(documentsRefetchInterval([doc('ready'), doc('failed')])).toBe(false)
  })

  it('does not poll an empty or not-yet-loaded list', () => {
    expect(documentsRefetchInterval([])).toBe(false)
    expect(documentsRefetchInterval(undefined)).toBe(false)
  })
})
