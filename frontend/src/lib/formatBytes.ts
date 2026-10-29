const UNITS = ['B', 'KB', 'MB', 'GB']

/** 1536 -> "1.5 KB". At most one decimal, none when it would be ".0". */
export function formatBytes(bytes: number): string {
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${String(Math.round(value * 10) / 10)} ${UNITS[unit] ?? 'B'}`
}
