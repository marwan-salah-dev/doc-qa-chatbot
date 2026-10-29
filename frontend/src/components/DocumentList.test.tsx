// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { makeDocument, renderWithProviders } from '@/test/render'

import { DocumentList } from './DocumentList'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  remove: vi.fn(),
  reindex: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: { success: mocks.toastSuccess } }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      documents: {
        ...actual.api.documents,
        list: mocks.list,
        remove: mocks.remove,
        reindex: mocks.reindex,
      },
    },
  }
})

beforeEach(() => {
  vi.resetAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('DocumentList', () => {
  it('shows a status badge for each document', async () => {
    mocks.list.mockResolvedValue([
      makeDocument({ id: '1', filename: 'one.txt', status: 'ready' }),
      makeDocument({ id: '2', filename: 'two.txt', status: 'processing' }),
      makeDocument({ id: '3', filename: 'three.txt', status: 'pending' }),
      makeDocument({ id: '4', filename: 'four.txt', status: 'failed', error: 'No text found.' }),
    ])
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    for (const label of ['Ready', 'Processing', 'Pending', 'Failed']) {
      expect(await screen.findByText(label)).toBeTruthy()
    }
    expect(screen.getByText('one.txt')).toBeTruthy()
  })

  it('invites the user to upload when there are no documents', async () => {
    mocks.list.mockResolvedValue([])
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    expect(await screen.findByText(/No documents yet/)).toBeTruthy()
  })

  it('shows a load error with a retry', async () => {
    mocks.list.mockRejectedValueOnce(new ApiError(500, 'Database is down'))
    mocks.list.mockResolvedValue([makeDocument()])
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    expect(await screen.findByText('Database is down')).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('a.txt')).toBeTruthy()
  })

  it('shows why a document failed and reindexes it on request', async () => {
    const failed = makeDocument({ status: 'failed', error: 'No text found in this PDF.' })
    mocks.list.mockResolvedValue([failed])
    mocks.reindex.mockResolvedValue({ ...failed, status: 'pending', error: null })
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    expect(await screen.findByText('No text found in this PDF.')).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reindex a.txt' }))

    await waitFor(() => {
      expect(mocks.reindex).toHaveBeenCalledWith('ws1', 'd1')
    })
  })

  it('only offers Reindex on failed documents', async () => {
    mocks.list.mockResolvedValue([makeDocument({ status: 'ready' })])
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    await screen.findByText('a.txt')
    expect(screen.queryByRole('button', { name: /Reindex/ })).toBeNull()
  })

  it('shows a reindex error', async () => {
    mocks.list.mockResolvedValue([makeDocument({ status: 'failed', error: 'x' })])
    mocks.reindex.mockRejectedValue(new ApiError(409, 'This document is already being indexed.'))
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Reindex a.txt' }))

    expect(await screen.findByText('This document is already being indexed.')).toBeTruthy()
  })

  it('deletes only after the confirm dialog is accepted', async () => {
    const user = userEvent.setup()
    mocks.list.mockResolvedValue([makeDocument()])
    mocks.remove.mockResolvedValue(undefined)
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    await user.click(await screen.findByRole('button', { name: 'Delete a.txt' }))
    let dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Delete a\.txt\?/)).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
    expect(mocks.remove).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Delete a.txt' }))
    dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(mocks.remove).toHaveBeenCalledWith('ws1', 'd1')
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Deleted a.txt')
  })

  it('keeps the dialog open and shows the error when a delete fails', async () => {
    const user = userEvent.setup()
    mocks.list.mockResolvedValue([makeDocument()])
    mocks.remove.mockRejectedValue(new ApiError(500, 'The vector store is unavailable.'))
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    await user.click(await screen.findByRole('button', { name: 'Delete a.txt' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(await within(dialog).findByText('The vector store is unavailable.')).toBeTruthy()
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(mocks.toastSuccess).not.toHaveBeenCalled()
  })

  it('polls while a document is processing and stops once all have settled', async () => {
    // shouldAdvanceTime keeps Testing Library's own waiting working under fake timers
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mocks.list
      .mockResolvedValueOnce([makeDocument({ status: 'processing' })])
      .mockResolvedValue([makeDocument({ status: 'ready' })])
    renderWithProviders(<DocumentList workspaceId="ws1" />)

    expect(await screen.findByText('Processing')).toBeTruthy()
    expect(mocks.list).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2100)
    expect(await screen.findByText('Ready')).toBeTruthy()
    expect(mocks.list).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(20_000)
    expect(mocks.list).toHaveBeenCalledTimes(2)
  })
})
