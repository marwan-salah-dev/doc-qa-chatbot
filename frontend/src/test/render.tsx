import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'

import type { Citation, DocumentItem, Message, Workspace } from '@/api/types'

import { LocationProbe } from './LocationProbe'

/** Renders at `route` with a fresh query cache that never retries (so errors show at once).
 * `/` renders a marker, so a test can tell that something navigated away. The conversation
 * route is nested under the workspace one, as in the app, so `ui` stays mounted when the
 * conversation changes. */
export function renderWithProviders(ui: ReactElement, route = '/w/ws1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/" element={<p>Home page</p>} />
          <Route path="/w/:workspaceId" element={ui}>
            <Route path="c/:conversationId" element={null} />
          </Route>
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...view, queryClient }
}

export function makeDocument(overrides: Partial<DocumentItem> = {}): DocumentItem {
  return {
    id: 'd1',
    workspace_id: 'ws1',
    filename: 'a.txt',
    content_type: 'text/plain',
    size_bytes: 2048,
    sha256: 'a'.repeat(64),
    status: 'ready',
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function makeWorkspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    id: 'ws1',
    name: 'Acme Dental',
    created_at: '2026-01-01T00:00:00Z',
    starter_questions: [],
    ...overrides,
  }
}

export function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    number: 1,
    document_id: 'd1',
    filename: 'faq.txt',
    location: { kind: 'txt', start: 3, end: 8 },
    label: 'lines 3–8',
    text: 'We are open Monday to Friday, 9am to 5pm.',
    score: 0.82,
    ...overrides,
  }
}

export function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'We are open 9am to 5pm [1].',
    citations: [makeCitation()],
    refused: false,
    uncited: false,
    incomplete: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}
