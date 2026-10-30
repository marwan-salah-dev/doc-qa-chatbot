import { type ComponentProps, createContext, useContext, useMemo } from 'react'
import ReactMarkdown, { type Components, type Options } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { Citation } from '@/api/types'
import { CitationChip } from '@/components/CitationChip'
import { citationNumberFromHref, numberCitationsByFirstUse, remarkCitations } from '@/lib/citations'

const CitationsContext = createContext<ReadonlyMap<number, Citation>>(new Map())

/** Citation links (from `remarkCitations`) become chips; every other link opens in a new tab. */
function Link({ href, title, children }: ComponentProps<'a'>) {
  const citations = useContext(CitationsContext)
  const number = citationNumberFromHref(href)
  const citation = number === null ? undefined : citations.get(number)
  if (citation) return <CitationChip citation={citation} />
  return (
    <a href={href} title={title} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  )
}

const components: Components = { a: Link }

interface MarkdownProps {
  text: string
  /** The sources `[n]` markers may cite; markers without one stay as text. */
  citations?: Citation[]
}

const NO_CITATIONS: Citation[] = []

/** An answer rendered as GitHub-flavoured markdown. Raw HTML is never rendered (there is no
 * rehype-raw), so it shows as text, and react-markdown's default URL check drops `javascript:`
 * links. Citation chips are numbered 1, 2, 3 in order of first use, as in the Sources list. */
export function Markdown({ text, citations = NO_CITATIONS }: MarkdownProps) {
  const byNumber = useMemo(() => numberCitationsByFirstUse(text, citations), [text, citations])
  const remarkPlugins = useMemo<Options['remarkPlugins']>(
    () => [remarkGfm, [remarkCitations, { numbers: new Set(byNumber.keys()) }]],
    [byNumber],
  )

  return (
    <CitationsContext value={byNumber}>
      <div className="markdown">
        <ReactMarkdown remarkPlugins={remarkPlugins} components={components}>
          {text}
        </ReactMarkdown>
      </div>
    </CitationsContext>
  )
}
