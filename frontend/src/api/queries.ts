import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { Workspace } from './types'

/** Every query key in one place, so invalidation can't drift from the queries. Documents and
 * conversations are added with their UI in steps 13-14. */
export const queryKeys = {
  workspaces: () => ['workspaces'] as const,
}

export function useWorkspaces() {
  return useQuery({ queryKey: queryKeys.workspaces(), queryFn: api.workspaces.list })
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.workspaces.create(name),
    onSuccess: async (workspace) => {
      // Show it straight away (the caller navigates to it), then refetch for the real order
      queryClient.setQueryData<Workspace[]>(queryKeys.workspaces(), (old) => [
        ...(old ?? []),
        workspace,
      ])
      await queryClient.invalidateQueries({ queryKey: queryKeys.workspaces() })
    },
  })
}
