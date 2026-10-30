/** This browser's visitor id for the public demo, sent as `X-Visitor-Id` with every API call.
 *
 * There is no login: the server keeps a hash of this id on the workspaces and chats it creates
 * and only shows them to requests carrying the same id. It is random (`crypto.randomUUID()`) and
 * acts like a password, so it is never shown or logged. Kept in localStorage so a reload keeps
 * the same workspaces; if storage is blocked it lasts for this page only. */

export const VISITOR_STORAGE_KEY = 'docqa.visitorId'
export const VISITOR_HEADER = 'X-Visitor-Id'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

let current: string | undefined

export function visitorId(): string {
  if (current) return current
  try {
    const stored = globalThis.localStorage.getItem(VISITOR_STORAGE_KEY)
    if (stored && UUID.test(stored)) current = stored
  } catch {
    // Blocked storage (private mode, tests without a DOM): fall through to a fresh id
  }
  if (!current) {
    current = crypto.randomUUID()
    try {
      globalThis.localStorage.setItem(VISITOR_STORAGE_KEY, current)
    } catch {
      // Kept in memory only
    }
  }
  return current
}

/** Headers every API request carries. */
export function apiHeaders(): Record<string, string> {
  return { [VISITOR_HEADER]: visitorId() }
}

export function resetVisitorIdForTests(): void {
  current = undefined
}
