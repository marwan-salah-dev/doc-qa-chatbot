export type ThemePreference = 'light' | 'dark' | 'system'
export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'
// Keep in step with the inline script in index.html, which applies the theme before first paint
const PREFERENCES: readonly string[] = ['light', 'dark', 'system']

interface ThemeStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

interface ThemeRoot {
  classList: { toggle: (name: string, on: boolean) => unknown }
  style: { colorScheme: string }
}

export function resolveTheme(preference: ThemePreference, systemDark: boolean): Theme {
  if (preference === 'system') return systemDark ? 'dark' : 'light'
  return preference
}

/** The saved choice, or "system" when there is none or storage is blocked (private windows). */
export function readThemePreference(storage: ThemeStorage = localStorage): ThemePreference {
  try {
    const saved = storage.getItem(STORAGE_KEY)
    return saved && PREFERENCES.includes(saved) ? (saved as ThemePreference) : 'system'
  } catch {
    return 'system'
  }
}

export function writeThemePreference(
  preference: ThemePreference,
  storage: ThemeStorage = localStorage,
) {
  try {
    storage.setItem(STORAGE_KEY, preference)
  } catch {
    // Blocked storage only means the choice isn't remembered next time
  }
}

/** Tailwind's `dark:` variant keys off the `.dark` class; colorScheme styles native controls. */
export function applyTheme(theme: Theme, root: ThemeRoot = document.documentElement) {
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
}
