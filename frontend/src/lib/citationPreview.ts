import type { Location } from '@/api/types'

/** The PDF pages a citation covers: its page, or every page of a chunk that crosses pages. */
export function citedPages(location: Location): number[] {
  const first = location.page
  if (location.kind !== 'pdf' || first == null) return []
  const last = Math.max(first, location.page_end ?? first)
  return Array.from({ length: last - first + 1 }, (_, i) => first + i)
}

export interface ContextLine {
  /** 1-based, as in the original file and the citation's line range */
  number: number
  text: string
  cited: boolean
}

/** Lines `start`..`end` of a text file plus `context` lines either side. Empty when the range
 * is outside the file, which means the file no longer matches what was indexed. */
export function lineWindow(text: string, start: number, end: number, context = 3): ContextLine[] {
  const lines = text.split(/\r\n|\r|\n/)
  if (start < 1 || start > lines.length || end < start) return []
  const from = Math.max(1, start - context)
  const to = Math.min(lines.length, end + context)
  return lines.slice(from - 1, to).map((line, i) => {
    const number = from + i
    return { number, text: line, cited: number >= start && number <= end }
  })
}

// Shorter pieces ("to", "a 9") appear in almost any passage, so marking them would mislead
const MIN_HIGHLIGHT_CHARS = 4

function normalize(text: string): string {
  return text.replace(/\s+/g, ' ').trim().toLowerCase()
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** One text item of a PDF page as HTML for react-pdf's text layer, marked when it is part of
 * the cited passage. pdf.js splits pages into runs of text, so a run is marked when its text
 * appears in the passage (ignoring spacing and case). The text is escaped because the text
 * layer renders this as markup. */
export function highlightTextItem(item: string, passage: string): string {
  const escaped = escapeHtml(item)
  const needle = normalize(item)
  if (needle.replace(/ /g, '').length < MIN_HIGHLIGHT_CHARS) return escaped
  return normalize(passage).includes(needle) ? `<mark>${escaped}</mark>` : escaped
}
