// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queries'
import type { Workspace } from '@/api/types'
import { makeWorkspace, renderWithProviders } from '@/test/render'

import { WorkspaceHeader } from './WorkspaceHeader'

const mocks = vi.hoisted(() => ({ rename: vi.fn(), remove: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      workspaces: { ...actual.api.workspaces, rename: mocks.rename, remove: mocks.remove },
    },
  }
})

const workspace = makeWorkspace()

function renderHeader() {
  const view = renderWithProviders(<WorkspaceHeader workspace={workspace} />)
  view.queryClient.setQueryData<Workspace[]>(queryKeys.workspaces(), [
    workspace,
    makeWorkspace({ id: 'ws2', name: 'Other' }),
  ])
  return view
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('WorkspaceHeader', () => {
  it('shows the workspace name', () => {
    renderHeader()
    expect(screen.getByRole('heading', { name: 'Acme Dental' })).toBeTruthy()
  })

  it('renames with a prefilled, trimmed name', async () => {
    const user = userEvent.setup()
    mocks.rename.mockResolvedValue({ ...workspace, name: 'New name' })
    renderHeader()

    await user.click(screen.getByRole('button', { name: 'Rename workspace' }))
    const dialog = await screen.findByRole('dialog')
    const input = within(dialog).getByLabelText<HTMLInputElement>('Name')
    expect(input.value).toBe('Acme Dental')
    await user.clear(input)
    await user.type(input, '  New name  ')
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(mocks.rename).toHaveBeenCalledWith('ws1', 'New name')
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
  })

  it('does not allow saving an empty name', async () => {
    const user = userEvent.setup()
    renderHeader()

    await user.click(screen.getByRole('button', { name: 'Rename workspace' }))
    const dialog = await screen.findByRole('dialog')
    await user.clear(within(dialog).getByLabelText('Name'))

    expect(within(dialog).getByRole<HTMLButtonElement>('button', { name: 'Save' }).disabled).toBe(
      true,
    )
  })

  it('shows a rename error and keeps the dialog open', async () => {
    const user = userEvent.setup()
    mocks.rename.mockRejectedValue(new ApiError(500, 'Could not rename.'))
    renderHeader()

    await user.click(screen.getByRole('button', { name: 'Rename workspace' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Name'), '!')
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    expect(await within(dialog).findByText('Could not rename.')).toBeTruthy()
  })

  it('deletes after confirmation, drops it from the cache and navigates away', async () => {
    const user = userEvent.setup()
    mocks.remove.mockResolvedValue(undefined)
    const { queryClient } = renderHeader()

    await user.click(screen.getByRole('button', { name: 'Delete workspace' }))
    const dialog = await screen.findByRole('dialog')
    expect(mocks.remove).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Home page')).toBeTruthy()
    expect(mocks.remove).toHaveBeenCalledWith('ws1')
    expect(queryClient.getQueryData<Workspace[]>(queryKeys.workspaces())?.map((w) => w.id)).toEqual(
      ['ws2'],
    )
  })

  it('stays put and shows the error when the delete fails', async () => {
    const user = userEvent.setup()
    mocks.remove.mockRejectedValue(new ApiError(500, 'Delete failed.'))
    renderHeader()

    await user.click(screen.getByRole('button', { name: 'Delete workspace' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(await within(dialog).findByText('Delete failed.')).toBeTruthy()
    expect(screen.queryByText('Home page')).toBeNull()
  })
})
