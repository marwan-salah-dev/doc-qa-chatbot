import { describe, expect, it } from 'vitest'

import { applyTheme, readThemePreference, resolveTheme, writeThemePreference } from './theme'

function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
    values,
  }
}

const brokenStorage = {
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('theme', () => {
  it('follows the system unless light or dark is chosen', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
  })

  it('reads a saved preference and ignores anything else', () => {
    expect(readThemePreference(memoryStorage({ theme: 'dark' }))).toBe('dark')
    expect(readThemePreference(memoryStorage({ theme: 'purple' }))).toBe('system')
    expect(readThemePreference(memoryStorage())).toBe('system')
  })

  it('saves the preference', () => {
    const storage = memoryStorage()
    writeThemePreference('light', storage)
    expect(storage.values.get('theme')).toBe('light')
  })

  it('falls back to the system theme when storage is blocked', () => {
    expect(readThemePreference(brokenStorage)).toBe('system')
    expect(() => {
      writeThemePreference('dark', brokenStorage)
    }).not.toThrow()
  })

  it('sets the dark class and colour scheme on the root element', () => {
    const classes = new Set<string>()
    const root = {
      classList: {
        toggle: (name: string, on: boolean) => {
          if (on) classes.add(name)
          else classes.delete(name)
        },
      },
      style: { colorScheme: '' },
    }

    applyTheme('dark', root)
    expect(classes.has('dark')).toBe(true)
    expect(root.style.colorScheme).toBe('dark')

    applyTheme('light', root)
    expect(classes.has('dark')).toBe(false)
    expect(root.style.colorScheme).toBe('light')
  })
})
