import { createBrowserRouter } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { HomePage } from '@/pages/HomePage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { WorkspacePage } from '@/pages/WorkspacePage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      {
        path: 'w/:workspaceId',
        element: <WorkspacePage />,
        // Nested, so opening a conversation keeps the page (and a streaming reply) mounted;
        // WorkspacePage reads the id itself rather than rendering an outlet
        children: [{ path: 'c/:conversationId', element: null }],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
