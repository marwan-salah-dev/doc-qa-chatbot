// Mirrors the backend's response models. Source of truth: backend/app/api/schemas.py
// (and `citation_dict` / `_to_sse` for the streamed events). Datetimes are ISO strings.

/** Server settings the UI needs to match (GET /config). */
export interface AppConfig {
  max_upload_mb: number
  /** The longest question the chat endpoint accepts. */
  max_question_chars: number
  /** The public demo: the seeded demo workspace is read-only and visitor workspaces expire. */
  public_demo: boolean
}

export interface Workspace {
  id: string
  name: string
  created_at: string
  /** Suggested first questions for a new chat; empty except in the seeded demo workspace */
  starter_questions: string[]
  /** The seeded demo workspace (read-only for visitors on the public demo) */
  is_demo: boolean
  /** When a visitor's workspace on the public demo is deleted; null = kept */
  expires_at: string | null
}

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface DocumentItem {
  id: string
  workspace_id: string
  filename: string
  content_type: string
  size_bytes: number
  /** Hex SHA-256 of the file */
  sha256: string
  status: DocumentStatus
  /** Why ingestion failed; safe to show. Only set when `status` is "failed". */
  error: string | null
  created_at: string
}

export interface Conversation {
  id: string
  workspace_id: string
  /** The first question, shortened; empty until one is asked. */
  title: string
  created_at: string
}

export type FileKind = 'pdf' | 'docx' | 'txt'

/** Where a source sits in its file. Which fields are set depends on `kind`:
 * PDF uses `page` (and `page_end` when a chunk crosses pages), DOCX `heading` plus a paragraph
 * range in `start`/`end`, TXT a line range in `start`/`end`. */
export interface Location {
  kind: FileKind
  page?: number | null
  page_end?: number | null
  heading?: string | null
  start?: number | null
  end?: number | null
}

/** A source given to the model as `[number]`. `label` is the location in words. */
export interface Citation {
  number: number
  document_id: string
  filename: string
  location: Location
  label: string
  text: string
  score: number
}

export type MessageRole = 'user' | 'assistant'

export interface Message {
  id: string
  role: MessageRole
  content: string
  citations: Citation[]
  /** The answer was the fixed "not found in the documents" reply. */
  refused: boolean
  /** The model answered without citing any source. */
  uncited: boolean
  /** The reply was stopped before it finished. */
  incomplete: boolean
  created_at: string
}

/** Payload of the `done` event: both messages are saved. */
export interface ReplyDone {
  user_message_id: string
  message_id: string
  /** Only the sources the answer actually cites. */
  citations: Citation[]
  refused: boolean
  uncited: boolean
}
