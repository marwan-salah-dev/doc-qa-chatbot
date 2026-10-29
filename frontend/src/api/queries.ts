import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { DocumentItem, Workspace } from './types'

/** Every query key in one place, so invalidation can't drift from the queries. Conversations
 * are added with their UI in step 14. */
export const queryKeys = {
  config: () => ['config'] as const,
  workspaces: () => ['workspaces'] as const,
  // Not nested under 'workspaces': invalidating the workspace list must not refetch documents
  documents: (workspaceId: string) => ['documents', workspaceId] as const,
}

const DOCUMENT_POLL_MS = 2000

/** How long to wait before refetching the document list: only while something is still being
 * indexed, so a settled list costs no requests. */
export function documentsRefetchInterval(documents: DocumentItem[] | undefined): number | false {
  const busy = documents?.some((d) => d.status === 'pending' || d.status === 'processing')
  return busy ? DOCUMENT_POLL_MS : false
}

export function useConfig() {
  // The server's settings only change with a restart
  return useQuery({ queryKey: queryKeys.config(), queryFn: api.config.get, staleTime: Infinity })
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

export function useRenameWorkspace(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.workspaces.rename(workspaceId, name),
    onSuccess: async (workspace) => {
      queryClient.setQueryData<Workspace[]>(queryKeys.workspaces(), (old) =>
        old?.map((w) => (w.id === workspace.id ? workspace : w)),
      )
      await queryClient.invalidateQueries({ queryKey: queryKeys.workspaces() })
    },
  })
}

export function useDeleteWorkspace(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.workspaces.remove(workspaceId),
    onSuccess: () => {
      // Dropped from the cache before the caller navigates away: the home page opens the first
      // workspace in the list, which would otherwise still be this deleted one.
      queryClient.setQueryData<Workspace[]>(queryKeys.workspaces(), (old) =>
        old?.filter((w) => w.id !== workspaceId),
      )
      queryClient.removeQueries({ queryKey: queryKeys.documents(workspaceId) })
    },
  })
}

export function useDocuments(workspaceId: string) {
  return useQuery({
    queryKey: queryKeys.documents(workspaceId),
    queryFn: () => api.documents.list(workspaceId),
    refetchInterval: (query) => documentsRefetchInterval(query.state.data),
  })
}

export function useUploadDocument(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.documents.upload(workspaceId, file),
    // The new document starts as pending, so the refetch also starts the polling
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) }),
  })
}

export function useReindexDocument(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId: string) => api.documents.reindex(workspaceId, documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) }),
  })
}

export function useDeleteDocument(workspaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId: string) => api.documents.remove(workspaceId, documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) }),
  })
}
