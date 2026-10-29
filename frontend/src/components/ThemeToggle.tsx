import { MonitorIcon, MoonIcon, SunIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { ThemePreference } from '@/lib/theme'

/** Cycles system → light → dark. */
export function ThemeToggle({
  preference,
  onCycle,
}: {
  preference: ThemePreference
  onCycle: () => void
}) {
  const Icon = preference === 'system' ? MonitorIcon : preference === 'light' ? SunIcon : MoonIcon
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={`Theme: ${preference}. Change theme`}
      title={`Theme: ${preference}`}
      onClick={onCycle}
    >
      <Icon />
    </Button>
  )
}
