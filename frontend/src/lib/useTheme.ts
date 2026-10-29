import { useEffect, useState } from 'react'

import {
  applyTheme,
  readThemePreference,
  resolveTheme,
  type ThemePreference,
  writeThemePreference,
} from '@/lib/theme'
import { useMediaQuery } from '@/lib/useMediaQuery'

const NEXT: Record<ThemePreference, ThemePreference> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
}

/** The saved theme choice and the theme it resolves to; "system" follows the OS as it changes. */
export function useTheme() {
  const [preference, setPreference] = useState(readThemePreference)
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)')
  const theme = resolveTheme(preference, systemDark)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  function cycle() {
    const next = NEXT[preference]
    writeThemePreference(next)
    setPreference(next)
  }

  return { preference, theme, cycle }
}
