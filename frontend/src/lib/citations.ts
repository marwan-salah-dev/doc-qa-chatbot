import type { Citation } from '@/api/types'

/** `[1]`, `[1, 3]` and gpt-oss's `[1†source]`; `[1][3]` is two matches. Mirrors `_MARKER` in
 * backend/app/services/rag.py, so the UI links exactly the markers the backend counts. */
const MARKER = /\[(\d+(?:\s*,\s*\d+)*)(?:†[^\]\n]*)?\]/g

const HREF_PREFIX = '#cite-'

export function citationHref(number: number): string {
  return `${HREF_PREFIX}${String(number)}`
}

/** The source number of a citation link, or null for any other link. */
export function citationNumberFromHref(href: string | undefined): number | null {
  if (!href?.startsWith(HREF_PREFIX)) return null
  const number = Number(href.slice(HREF_PREFIX.length))
  return Number.isInteger(number) && number > 0 ? number : null
}

/** Splits text into plain parts and the source numbers its markers cite. Numbers with no
 * source are dropped (as the backend drops them), and a marker citing none stays as text. */
export function splitCitations(text: string, known: ReadonlySet<number>): (string | number)[] {
  const parts: (string | number)[] = []
  let plain = ''
  let last = 0
  for (const match of text.matchAll(MARKER)) {
    const numbers = (match[1] ?? '')
      .split(',')
      .map(Number)
      .filter((n) => known.has(n))
    if (numbers.length === 0) continue
    plain += text.slice(last, match.index)
    if (plain) parts.push(plain)
    plain = ''
    parts.push(...numbers)
    last = match.index + match[0].length
  }
  plain += text.slice(last)
  if (plain) parts.push(plain)
  return parts
}

/** The sources an answer cites, numbered 1, 2, 3 in the order the text first cites them, so an
 * answer never shows [1] and [3] without [2]. Keyed by the number in the text (what the model
 * wrote and what is saved); each value is the source with `number` set to the one to display.
 * Map order is first-use order. Worked out on every render, so live and saved answers match. */
export function numberCitationsByFirstUse(
  text: string,
  citations: readonly Citation[],
): Map<number, Citation> {
  const byNumber = new Map(citations.map((c) => [c.number, c]))
  const numbered = new Map<number, Citation>()
  for (const part of splitCitations(text, new Set(byNumber.keys()))) {
    const citation = typeof part === 'number' ? byNumber.get(part) : undefined
    if (citation && !numbered.has(citation.number)) {
      numbered.set(citation.number, { ...citation, number: numbered.size + 1 })
    }
  }
  return numbered
}

/** The few mdast fields this plugin touches (avoids depending on @types/mdast directly). */
interface MdNode {
  type: string
  value?: string
  url?: string
  children?: MdNode[]
}

export interface RemarkCitationsOptions {
  /** The source numbers that exist; other markers are left as text. */
  numbers: ReadonlySet<number>
}

/** A remark plugin that turns citation markers into `#cite-n` links, which `Markdown` renders
 * as chips. Only plain text is touched: code has its own node types, and text already inside a
 * link is skipped so links never nest. */
export function remarkCitations({ numbers }: RemarkCitationsOptions) {
  function visit(node: MdNode) {
    if (!node.children || node.type === 'link' || node.type === 'linkReference') return
    node.children = node.children.flatMap((child): MdNode[] => {
      if (child.type !== 'text' || child.value === undefined) {
        visit(child)
        return [child]
      }
      return splitCitations(child.value, numbers).map((part) =>
        typeof part === 'string'
          ? { type: 'text', value: part }
          : {
              type: 'link',
              url: citationHref(part),
              children: [{ type: 'text', value: String(part) }],
            },
      )
    })
  }
  return (tree: MdNode) => {
    visit(tree)
  }
}
