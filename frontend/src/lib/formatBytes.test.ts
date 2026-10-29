import { expect, it } from 'vitest'

import { formatBytes } from './formatBytes'

it.each([
  [0, '0 B'],
  [512, '512 B'],
  [1024, '1 KB'],
  [1536, '1.5 KB'],
  [20 * 1024 * 1024, '20 MB'],
])('formats %i bytes as %s', (bytes, text) => {
  expect(formatBytes(bytes)).toBe(text)
})
