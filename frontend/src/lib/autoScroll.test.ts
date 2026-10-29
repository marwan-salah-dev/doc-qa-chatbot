import { describe, expect, it } from 'vitest'

import { isNearBottom } from './autoScroll'

describe('isNearBottom', () => {
  it('is true at the very bottom', () => {
    expect(isNearBottom({ scrollTop: 600, scrollHeight: 1000, clientHeight: 400 })).toBe(true)
  })

  it('is true within the threshold', () => {
    expect(isNearBottom({ scrollTop: 540, scrollHeight: 1000, clientHeight: 400 })).toBe(true)
  })

  it('is false once the user has scrolled up', () => {
    expect(isNearBottom({ scrollTop: 300, scrollHeight: 1000, clientHeight: 400 })).toBe(false)
  })

  it('is true when everything fits', () => {
    expect(isNearBottom({ scrollTop: 0, scrollHeight: 300, clientHeight: 400 })).toBe(true)
  })
})
