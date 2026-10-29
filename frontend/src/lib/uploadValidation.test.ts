import { describe, expect, it } from 'vitest'

import { validateFile } from './uploadValidation'

const MB = 1024 * 1024

function file(name: string, size = 100) {
  return { name, size }
}

describe('validateFile', () => {
  it.each(['a.pdf', 'a.docx', 'a.txt', 'REPORT.PDF', 'Notes.Txt', 'my.file.name.docx'])(
    'accepts %s',
    (name) => {
      expect(validateFile(file(name), 20)).toBeNull()
    },
  )

  it.each(['a.png', 'a.doc', 'noextension', 'a.pdf.exe', '.pdf'])('rejects %s by type', (name) => {
    expect(validateFile(file(name), 20)).toMatch(/PDF, DOCX or TXT/)
  })

  it('rejects an empty file', () => {
    expect(validateFile(file('a.txt', 0), 20)).toMatch(/empty/i)
  })

  it('accepts a file exactly at the limit and rejects one byte over', () => {
    expect(validateFile(file('a.txt', 20 * MB), 20)).toBeNull()
    expect(validateFile(file('a.txt', 20 * MB + 1), 20)).toMatch(/20 MB/)
  })

  it('skips the size check while the limit is unknown (the server still enforces it)', () => {
    expect(validateFile(file('a.txt', 500 * MB), undefined)).toBeNull()
  })
})
