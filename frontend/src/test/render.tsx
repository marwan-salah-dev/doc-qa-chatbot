import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'

import type { DocumentItem, Workspace } from '@/api/types'

/** Renders at `route` with a fresh query cache that never retries (so errors show at once).
 * `/` renders a marker, so a test can tell that something navigated away. */
export function renderWithProviders(ui: ReactElement, route = '/w/ws1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/" element={<p>Home page</p>} />
          <Route path="/w/:workspaceId" element={ui} />
        </Routes>
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
    status: 'ready',
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function makeWorkspace(overrides: Partial<Workspace> = {}): Workspace {
  return { id: 'ws1', name: 'Acme Dental', created_at: '2026-01-01T00:00:00Z', ...overrides }
}
