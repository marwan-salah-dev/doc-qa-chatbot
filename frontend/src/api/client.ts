import type { Conversation, DocumentItem, Message, Workspace } from './types'

const configuredBase = import.meta.env.VITE_API_BASE_URL

/** In development the Vite dev server proxies /api to the backend (see vite.config.ts). */
export const API_BASE = configuredBase ? configuredBase.replace(/\/$/, '') : '/api'

/** A failed API call. `message` is always safe to show to users. */
export class ApiError extends Error {
  readonly status: number
  /** FastAPI's raw `detail`, for callers that need more than the message. */
  readonly detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** Builds an API path, URL-encoding every interpolated value. */
export function apiPath(strings: TemplateStringsArray, ...values: string[]): string {
  return strings.reduce(
    (path, part, i) => path + part + (i < values.length ? encodeURIComponent(values[i] ?? '') : ''),
    API_BASE,
  )
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let detail: unknown
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail
  } catch {
    detail = undefined
  }
  const message =
    messageFromDetail(detail) ??
    `Something went wrong (${String(response.status)}). Please try again.`
  return new ApiError(response.status, message, detail)
}

/** FastAPI sends `detail` as a string for HTTPException and as a list for validation errors. */
function messageFromDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const first: unknown = detail[0]
    if (first && typeof first === 'object' && 'msg' in first && typeof first.msg === 'string') {
      return first.msg
    }
  }
  return undefined
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  // FormData bodies must set their own multipart boundary, so only JSON gets a header
  if (typeof init.body === 'string') headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) throw await errorFromResponse(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function withJson(method: string, body: unknown): RequestInit {
  return { method, body: JSON.stringify(body) }
}

export const api = {
  workspaces: {
    list: () => request<Workspace[]>(apiPath`/workspaces`),
    get: (id: string) => request<Workspace>(apiPath`/workspaces/${id}`),
    create: (name: string) => request<Workspace>(apiPath`/workspaces`, withJson('POST', { name })),
    rename: (id: string, name: string) =>
      request<Workspace>(apiPath`/workspaces/${id}`, withJson('PATCH', { name })),
    remove: (id: string) => request<undefined>(apiPath`/workspaces/${id}`, { method: 'DELETE' }),
  },

  documents: {
    list: (workspaceId: string) =>
      request<DocumentItem[]>(apiPath`/workspaces/${workspaceId}/documents`),
    get: (workspaceId: string, id: string) =>
      request<DocumentItem>(apiPath`/workspaces/${workspaceId}/documents/${id}`),
    /** Accepted for background ingestion; poll the document until it is ready or failed. */
    upload: (workspaceId: string, file: File) => {
      const body = new FormData()
      body.append('file', file)
      return request<DocumentItem>(apiPath`/workspaces/${workspaceId}/documents`, {
        method: 'POST',
        body,
      })
    },
    remove: (workspaceId: string, id: string) =>
      request<undefined>(apiPath`/workspaces/${workspaceId}/documents/${id}`, {
        method: 'DELETE',
      }),
    reindex: (workspaceId: string, id: string) =>
      request<DocumentItem>(apiPath`/workspaces/${workspaceId}/documents/${id}/reindex`, {
        method: 'POST',
      }),
    /** The original file, for previews and downloads. */
    fileUrl: (workspaceId: string, id: string) =>
      apiPath`/workspaces/${workspaceId}/documents/${id}/file`,
  },

  conversations: {
    list: (workspaceId: string) =>
      request<Conversation[]>(apiPath`/workspaces/${workspaceId}/conversations`),
    create: (workspaceId: string) =>
      request<Conversation>(apiPath`/workspaces/${workspaceId}/conversations`, {
        method: 'POST',
      }),
    remove: (workspaceId: string, id: string) =>
      request<undefined>(apiPath`/workspaces/${workspaceId}/conversations/${id}`, {
        method: 'DELETE',
      }),
    messages: (workspaceId: string, id: string) =>
      request<Message[]>(apiPath`/workspaces/${workspaceId}/conversations/${id}/messages`),
  },
}
