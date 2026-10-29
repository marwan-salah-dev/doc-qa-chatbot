import { afterEach } from 'vitest'

// Vitest has no globals here, so Testing Library can't register its own cleanup.
afterEach(async () => {
  if (typeof document === 'undefined') return
  const { cleanup } = await import('@testing-library/react')
  cleanup()
})
