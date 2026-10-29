import type { DocumentItem } from '@/api/types'

/** Why a question can't be sent yet, or undefined when it can. Answers come only from ready
 * documents, so asking before one is ready would always be refused. */
export function sendBlockedReason(documents: DocumentItem[] | undefined): string | undefined {
  if (!documents) return 'Loading documents…'
  if (documents.length === 0) return 'Upload a document to start asking questions.'
  if (documents.some((d) => d.status === 'ready')) return undefined
  if (documents.some((d) => d.status === 'pending' || d.status === 'processing')) {
    return 'Your documents are still being indexed. You can ask once one is ready.'
  }
  return 'Your documents could not be indexed. Reindex them or upload another file to ask questions.'
}
