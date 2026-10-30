import { describe, expect, it } from 'vitest'

import { makeCitation } from '@/test/render'

import {
  citationHref,
  citationNumberFromHref,
  numberCitationsByFirstUse,
  splitCitations,
} from './citations'

const known = new Set([1, 2, 3])

describe('splitCitations', () => {
  it('turns a marker into its source number', () => {
    expect(splitCitations('Open 9 to 5 [1].', known)).toEqual(['Open 9 to 5 ', 1, '.'])
  })

  it('splits a grouped marker into one number each', () => {
    expect(splitCitations('Yes [1, 3]', known)).toEqual(['Yes ', 1, 3])
  })

  it('reads adjacent markers as two', () => {
    expect(splitCitations('Yes [1][3]', known)).toEqual(['Yes ', 1, 3])
  })

  it("ignores the part after gpt-oss's dagger", () => {
    expect(splitCitations('Yes [2†source]', known)).toEqual(['Yes ', 2])
  })

  it('leaves markers with no matching source alone', () => {
    expect(splitCitations('See [7] and [1, 7]', known)).toEqual(['See [7] and ', 1])
  })

  it('returns text without markers unchanged', () => {
    expect(splitCitations('Plain text', known)).toEqual(['Plain text'])
  })
})

describe('numberCitationsByFirstUse', () => {
  const source = (number: number) => makeCitation({ number, filename: `doc${String(number)}.txt` })

  it('numbers the cited sources 1, 2, 3 in the order the answer first cites them', () => {
    const numbered = numberCitationsByFirstUse('Cards [3]. Hours [1, 3]. Fees [4].', [
      source(1),
      source(3),
      source(4),
    ])

    // Keyed by the number in the text; the value is the source with its number for display
    expect([...numbered.keys()]).toEqual([3, 1, 4])
    expect([...numbered.values()].map((c) => [c.number, c.filename])).toEqual([
      [1, 'doc3.txt'],
      [2, 'doc1.txt'],
      [3, 'doc4.txt'],
    ])
  })

  it('leaves out sources the answer never cites, and markers with no source', () => {
    const numbered = numberCitationsByFirstUse('Only [2] and [9].', [source(1), source(2)])

    expect([...numbered.entries()].map(([marker, c]) => [marker, c.number])).toEqual([[2, 1]])
  })
})

describe('citation links', () => {
  it('round-trips a source number through its href', () => {
    expect(citationNumberFromHref(citationHref(3))).toBe(3)
  })

  it('ignores ordinary links', () => {
    expect(citationNumberFromHref('https://example.com')).toBeNull()
    expect(citationNumberFromHref('#cite-x')).toBeNull()
    expect(citationNumberFromHref(undefined)).toBeNull()
  })
})
