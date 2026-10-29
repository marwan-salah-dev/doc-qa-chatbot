import { describe, expect, it } from 'vitest'

import { citedPages, highlightTextItem, lineWindow } from './citationPreview'

describe('citedPages', () => {
  it('gives the single cited page', () => {
    expect(citedPages({ kind: 'pdf', page: 2 })).toEqual([2])
  })

  it('gives every page of a chunk that crosses pages', () => {
    expect(citedPages({ kind: 'pdf', page: 2, page_end: 4 })).toEqual([2, 3, 4])
  })

  it('gives nothing without a page or for other file types', () => {
    expect(citedPages({ kind: 'pdf' })).toEqual([])
    expect(citedPages({ kind: 'txt', start: 1, end: 2 })).toEqual([])
  })
})

describe('lineWindow', () => {
  const text = 'one\ntwo\r\nthree\nfour\nfive\nsix'

  it('numbers the cited lines and a few around them, as in the original file', () => {
    expect(lineWindow(text, 3, 4, 1)).toEqual([
      { number: 2, text: 'two', cited: false },
      { number: 3, text: 'three', cited: true },
      { number: 4, text: 'four', cited: true },
      { number: 5, text: 'five', cited: false },
    ])
  })

  it('stops at the start and end of the file', () => {
    expect(lineWindow(text, 1, 1, 2).map((l) => l.number)).toEqual([1, 2, 3])
    expect(lineWindow(text, 6, 6, 2).map((l) => l.number)).toEqual([4, 5, 6])
  })

  it('gives nothing when the range is outside the file (it changed since indexing)', () => {
    expect(lineWindow(text, 9, 10, 2)).toEqual([])
  })
})

describe('highlightTextItem', () => {
  const passage = 'Opening hours:\nMonday to Friday,   8am to 6pm. Saturday 9am to 1pm.'

  it('marks text that is part of the passage, ignoring spacing and case', () => {
    expect(highlightTextItem('monday to friday, 8am', passage)).toBe(
      '<mark>monday to friday, 8am</mark>',
    )
  })

  it('leaves other text alone', () => {
    expect(highlightTextItem('Emergency line', passage)).toBe('Emergency line')
  })

  it('does not mark tiny fragments that would match almost anywhere', () => {
    expect(highlightTextItem('to', passage)).toBe('to')
  })

  it('escapes HTML, since the PDF text layer renders the result as markup', () => {
    expect(highlightTextItem('<b>&', passage)).toBe('&lt;b&gt;&amp;')
    expect(highlightTextItem('<img>', '<img> tag')).toBe('<mark>&lt;img&gt;</mark>')
  })
})
