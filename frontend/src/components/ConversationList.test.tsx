// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import type { Conversation } from '@/api/types'
import { renderWithProviders } from '@/test/render'

import { ConversationList } from './ConversationList'

const mocks = vi.hoisted(() => ({ list: vi.fn(), remove: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      conversations: { ...actual.api.conversations, list: mocks.list, remove: mocks.remove },
    },
  }
})

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'c1',
    workspace_id: 'ws1',
    title: 'When are you open?',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('ConversationList', () => {
  it('lists conversations and marks the open one', async () => {
    mocks.list.mockResolvedValue([makeConversation(), makeConversation({ id: 'c2', title: '' })])
    renderWithProviders(<ConversationList workspaceId="ws1" />, '/w/ws1/c/c1')

    const open = await screen.findByRole('link', { name: 'When are you open?' })
    expect(open.getAttribute('aria-current')).toBe('page')
    expect(open.getAttribute('href')).toBe('/w/ws1/c/c1')
    // A conversation gets its title from the first question
    const untitled = screen.getByRole('link', { name: 'New conversation' })
    expect(untitled.getAttribute('aria-current')).toBeNull()
    expect(screen.getByRole('link', { name: /New chat/ }).getAttribute('href')).toBe('/w/ws1')
  })

  it('invites a first question when there are none', async () => {
    mocks.list.mockResolvedValue([])
    renderWithProviders(<ConversationList workspaceId="ws1" />)

    expect(await screen.findByText(/No conversations yet/)).toBeTruthy()
  })

  it('shows a load error with a retry', async () => {
    mocks.list.mockRejectedValueOnce(new ApiError(500, 'Database is down'))
    mocks.list.mockResolvedValue([makeConversation()])
    renderWithProviders(<ConversationList workspaceId="ws1" />)

    expect(await screen.findByText('Database is down')).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('When are you open?')).toBeTruthy()
  })

  it('deletes only after confirming, and leaves the conversation if it was open', async () => {
    const user = userEvent.setup()
    mocks.list.mockResolvedValue([makeConversation()])
    mocks.remove.mockResolvedValue(undefined)
    renderWithProviders(<ConversationList workspaceId="ws1" />, '/w/ws1/c/c1')

    await user.click(
      await screen.findByRole('button', { name: 'Delete conversation: When are you open?' }),
    )
    let dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
    expect(mocks.remove).not.toHaveBeenCalled()

    await user.click(
      screen.getByRole('button', { name: 'Delete conversation: When are you open?' }),
    )
    dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(mocks.remove).toHaveBeenCalledWith('ws1', 'c1')
    })
    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/w/ws1')
    })
  })

  it('stays put when another conversation is deleted', async () => {
    const user = userEvent.setup()
    mocks.list.mockResolvedValue([makeConversation(), makeConversation({ id: 'c2', title: 'B' })])
    mocks.remove.mockResolvedValue(undefined)
    renderWithProviders(<ConversationList workspaceId="ws1" />, '/w/ws1/c/c1')

    await user.click(await screen.findByRole('button', { name: 'Delete conversation: B' }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete' }),
    )

    await waitFor(() => {
      expect(mocks.remove).toHaveBeenCalledWith('ws1', 'c2')
    })
    expect(screen.getByTestId('location').textContent).toBe('/w/ws1/c/c1')
  })

  it("can't delete the conversation that is streaming a reply", async () => {
    mocks.list.mockResolvedValue([makeConversation()])
    renderWithProviders(<ConversationList workspaceId="ws1" busyId="c1" />, '/w/ws1/c/c1')

    const remove = await screen.findByRole('button', {
      name: 'Delete conversation: When are you open?',
    })
    expect((remove as HTMLButtonElement).disabled).toBe(true)
  })
})
