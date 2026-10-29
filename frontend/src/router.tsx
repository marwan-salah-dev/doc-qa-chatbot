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
      // Steps 13-14 add the conversation route under the workspace
      { path: 'w/:workspaceId', element: <WorkspacePage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
