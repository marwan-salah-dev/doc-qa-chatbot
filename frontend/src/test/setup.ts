import { afterEach, beforeEach } from 'vitest'

import { setMatchMedia } from './matchMedia'

// Component tests see the desktop layout unless they call setMatchMedia(false)
beforeEach(() => {
  if (typeof window !== 'undefined') setMatchMedia(true)
})

// Vitest has no globals here, so Testing Library can't register its own cleanup.
afterEach(async () => {
  if (typeof document === 'undefined') return
  const { cleanup } = await import('@testing-library/react')
  cleanup()
})
