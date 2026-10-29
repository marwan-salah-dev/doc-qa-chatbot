import { describe, expect, it } from 'vitest'

import { ApiError } from '@/api/client'

import { describeUploadError } from './uploadErrors'

describe('describeUploadError', () => {
  it('titles a duplicate and keeps the backend message', () => {
    const error = new ApiError(409, 'This file is already in the workspace as "a.txt".')
    expect(describeUploadError(error)).toEqual({
      title: 'Duplicate file',
      message: 'This file is already in the workspace as "a.txt".',
    })
  })

  it.each([
    [413, 'File too large'],
    [415, 'Unsupported file type'],
    [400, "Can't upload this file"],
  ])('titles a %i', (status, title) => {
    expect(describeUploadError(new ApiError(status, 'backend words')).title).toBe(title)
  })

  it('explains a 413 with no JSON body (e.g. from a proxy) instead of "Something went wrong"', () => {
    const error = new ApiError(413, 'Something went wrong (413). Please try again.')
    expect(describeUploadError(error, 20).message).toBe(
      'The file is larger than the 20 MB upload limit.',
    )
  })

  it('falls back to a generic title for other statuses', () => {
    const error = new ApiError(500, 'Boom')
    expect(describeUploadError(error)).toEqual({ title: 'Upload failed', message: 'Boom' })
  })

  it('handles a network failure', () => {
    expect(describeUploadError(new TypeError('Failed to fetch'))).toEqual({
      title: 'Upload failed',
      message: "Couldn't reach the server. Check your connection and try again.",
    })
  })
})
