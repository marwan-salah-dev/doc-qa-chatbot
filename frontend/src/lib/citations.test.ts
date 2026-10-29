import { describe, expect, it } from 'vitest'

import { citationHref, citationNumberFromHref, splitCitations } from './citations'

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
