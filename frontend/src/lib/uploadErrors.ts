import { ApiError } from '@/api/client'

export interface UploadErrorText {
  title: string
  message: string
}

const TITLES: Record<number, string> = {
  400: "Can't upload this file",
  409: 'Duplicate file',
  413: 'File too large',
  415: 'Unsupported file type',
}

/** A title and a message for a failed upload. The backend's own wording is used when it sent
 * any; a 413 from a proxy in front of it has no JSON body, so that one is worded here. */
export function describeUploadError(error: unknown, maxUploadMb?: number): UploadErrorText {
  if (!(error instanceof ApiError)) {
    return {
      title: 'Upload failed',
      message: "Couldn't reach the server. Check your connection and try again.",
    }
  }
  const title = TITLES[error.status] ?? 'Upload failed'
  if (error.status === 413 && error.detail === undefined) {
    const limit =
      maxUploadMb === undefined ? 'upload limit' : `${String(maxUploadMb)} MB upload limit`
    return { title, message: `The file is larger than the ${limit}.` }
  }
  return { title, message: error.message }
}
