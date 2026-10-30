// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { VISITOR_STORAGE_KEY, resetVisitorIdForTests, visitorId } from './visitor'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

beforeEach(() => {
  localStorage.clear()
  resetVisitorIdForTests()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('visitorId', () => {
  it('is a random UUID, kept in localStorage so a reload keeps the same workspaces', () => {
    const id = visitorId()

    expect(id).toMatch(UUID)
    expect(localStorage.getItem(VISITOR_STORAGE_KEY)).toBe(id)
    resetVisitorIdForTests()
    expect(visitorId()).toBe(id)
  })

  it('replaces a stored value that is not a UUID', () => {
    localStorage.setItem(VISITOR_STORAGE_KEY, 'tampered')

    expect(visitorId()).toMatch(UUID)
  })

  it('still works, for this page, when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    const id = visitorId()

    expect(id).toMatch(UUID)
    expect(visitorId()).toBe(id)
  })
})
