// @vitest-environment jsdom
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import type { DocumentItem } from '@/api/types'
import { makeDocument, renderWithProviders } from '@/test/render'

import { DocumentList } from './DocumentList'
import { DocumentUploader } from './DocumentUploader'

const mocks = vi.hoisted(() => ({ config: vi.fn(), list: vi.fn(), upload: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      config: { get: mocks.config },
      documents: { ...actual.api.documents, list: mocks.list, upload: mocks.upload },
    },
  }
})

// The picker's `accept` filter would stop user-event handing us the invalid files we want to test
const user = () => userEvent.setup({ applyAccept: false })

function textFile(name: string, content = 'hello') {
  return new File([content], name, { type: 'text/plain' })
}

function uploadedNames(): string[] {
  return mocks.upload.mock.calls.map((call) => (call[1] as File).name)
}

async function renderUploader() {
  renderWithProviders(<DocumentUploader workspaceId="ws1" />)
  // Once the hint shows the limit, the config has loaded and the size check is active
  await screen.findByText(/up to 1 MB/)
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.config.mockResolvedValue({ max_upload_mb: 1 })
  mocks.list.mockResolvedValue([])
  mocks.upload.mockImplementation((_ws: string, file: File) =>
    Promise.resolve(makeDocument({ filename: file.name })),
  )
})

describe('DocumentUploader', () => {
  it('uploads several picked files', async () => {
    await renderUploader()

    await user().upload(screen.getByLabelText('Choose files'), [
      textFile('a.txt'),
      textFile('b.pdf'),
    ])

    await waitFor(() => {
      expect(uploadedNames()).toEqual(['a.txt', 'b.pdf'])
    })
    expect(mocks.upload.mock.calls[0]?.[0]).toBe('ws1')
  })

  it('uploads one file at a time, in order', async () => {
    let finishFirst: (doc: DocumentItem) => void = () => undefined
    mocks.upload.mockReturnValueOnce(
      new Promise<DocumentItem>((resolve) => {
        finishFirst = resolve
      }),
    )
    await renderUploader()

    await user().upload(screen.getByLabelText('Choose files'), [
      textFile('a.txt'),
      textFile('b.txt'),
    ])

    await waitFor(() => {
      expect(uploadedNames()).toEqual(['a.txt'])
    })
    expect(await screen.findByText('Uploading…')).toBeTruthy()
    finishFirst(makeDocument({ filename: 'a.txt' }))
    await waitFor(() => {
      expect(uploadedNames()).toEqual(['a.txt', 'b.txt'])
    })
  })

  it('uploads dropped files and highlights the zone while dragging over it', async () => {
    await renderUploader()
    const zone = screen.getByRole('button', { name: /drop files here/i })

    fireEvent.dragOver(zone, { dataTransfer: { files: [] } })
    expect(zone.getAttribute('data-dragging')).toBe('true')
    fireEvent.dragLeave(zone)
    expect(zone.getAttribute('data-dragging')).toBe('false')

    fireEvent.drop(zone, { dataTransfer: { files: [textFile('dropped.txt')] } })

    await waitFor(() => {
      expect(uploadedNames()).toEqual(['dropped.txt'])
    })
  })

  it('rejects an unsupported type or oversized file without calling the server', async () => {
    await renderUploader()
    const big = new File([new Uint8Array(1024 * 1024 + 1)], 'big.txt')

    await user().upload(screen.getByLabelText('Choose files'), [textFile('photo.png'), big])

    expect(await screen.findByText(/Only PDF, DOCX or TXT/)).toBeTruthy()
    expect(await screen.findByText(/larger than the 1 MB/)).toBeTruthy()
    expect(mocks.upload).not.toHaveBeenCalled()
  })

  it.each([
    [409, 'Duplicate file', 'This file is already in the workspace as "a.txt".'],
    [413, 'File too large', 'The file is larger than the 1 MB upload limit.'],
    [415, 'Unsupported file type', 'Please upload a PDF, DOCX or TXT file.'],
    [400, "Can't upload this file", 'The file is empty.'],
  ])(
    'shows the backend %i error and still uploads the next file',
    async (status, title, message) => {
      mocks.upload.mockRejectedValueOnce(new ApiError(status, message))
      await renderUploader()

      await user().upload(screen.getByLabelText('Choose files'), [
        textFile('a.txt'),
        textFile('b.txt'),
      ])

      expect(await screen.findByText(title)).toBeTruthy()
      expect(await screen.findByText(message)).toBeTruthy()
      await waitFor(() => {
        expect(uploadedNames()).toEqual(['a.txt', 'b.txt'])
      })
    },
  )

  it('refreshes the document list after an upload so polling can start', async () => {
    // Only a mounted list is refetched, so render it alongside the uploader
    renderWithProviders(
      <>
        <DocumentUploader workspaceId="ws1" />
        <DocumentList workspaceId="ws1" />
      </>,
    )
    await screen.findByText(/No documents yet/)
    const callsBefore = mocks.list.mock.calls.length

    await user().upload(screen.getByLabelText('Choose files'), [textFile('a.txt')])

    await waitFor(() => {
      expect(mocks.list.mock.calls.length).toBeGreaterThan(callsBefore)
    })
  })
})
