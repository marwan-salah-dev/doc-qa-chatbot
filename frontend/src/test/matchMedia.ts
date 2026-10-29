/** jsdom has no `matchMedia`. This stub makes every media query report `matches`, and `set`
 * flips it and tells listeners, the way a window resize would. */
export function setMatchMedia(matches: boolean) {
  const listeners = new Set<() => void>()
  const state = { matches }
  window.matchMedia = (query: string) =>
    ({
      get matches() {
        return state.matches
      },
      media: query,
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    }) as unknown as MediaQueryList
  return {
    set(next: boolean) {
      state.matches = next
      listeners.forEach((listener) => {
        listener()
      })
    },
  }
}
