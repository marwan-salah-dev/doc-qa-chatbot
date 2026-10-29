import { createBrowserRouter } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { HomePage } from '@/pages/HomePage'
import { NotFoundPage } from '@/pages/NotFoundPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      {
        path: 'w/:workspaceId',
        // Loaded on demand: the chat brings markdown rendering and most of the UI, which the
        // first paint of the home page doesn't need
        lazy: async () => {
          const { WorkspacePage } = await import('@/pages/WorkspacePage')
          return { Component: WorkspacePage }
        },
        // Nested, so opening a conversation keeps the page (and a streaming reply) mounted;
        // WorkspacePage reads the id itself rather than rendering an outlet
        children: [{ path: 'c/:conversationId', element: null }],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
