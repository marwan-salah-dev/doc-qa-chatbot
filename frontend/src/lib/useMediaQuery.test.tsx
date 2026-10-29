// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { setMatchMedia } from '@/test/matchMedia'

import { useMediaQuery } from './useMediaQuery'

describe('useMediaQuery', () => {
  it('starts with the current match', () => {
    setMatchMedia(true)
    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))
    expect(result.current).toBe(true)
  })

  it('updates when the match changes', () => {
    const media = setMatchMedia(false)
    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))
    expect(result.current).toBe(false)

    act(() => {
      media.set(true)
    })
    expect(result.current).toBe(true)
  })
})
