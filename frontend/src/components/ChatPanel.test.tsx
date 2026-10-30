// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import type { StreamMessageOptions } from '@/api/stream'
import { setMatchMedia } from '@/test/matchMedia'
import { makeCitation, makeDocument, makeMessage, renderWithProviders } from '@/test/render'

import { ChatPanel } from './ChatPanel'

const mocks = vi.hoisted(() => ({
  config: vi.fn(),
  documents: vi.fn(),
  conversations: vi.fn(),
  create: vi.fn(),
  messages: vi.fn(),
  stream: vi.fn(),
  fileText: vi.fn(),
  fileExists: vi.fn(),
}))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      config: { get: mocks.config },
      documents: {
        ...actual.api.documents,
        list: mocks.documents,
        fileText: mocks.fileText,
        fileExists: mocks.fileExists,
      },
      conversations: {
        ...actual.api.conversations,
        list: mocks.conversations,
        create: mocks.create,
        messages: mocks.messages,
      },
    },
  }
})

vi.mock('@/api/stream', () => ({ streamMessage: mocks.stream }))

function renderPanel(route = '/w/ws1/c/c1', starterQuestions?: string[]) {
  return renderWithProviders(
    <ChatPanel workspaceId="ws1" starterQuestions={starterQuestions} />,
    route,
  )
}

const STARTERS = ['What are your opening hours?', 'Is there parking?']

async function ask(question: string) {
  const user = userEvent.setup()
  const box = await screen.findByRole('textbox', { name: 'Ask a question' })
  // Sending waits for the documents (an empty box keeps Send disabled, so wait on this instead)
  await waitFor(() => {
    expect(screen.queryByText('Loading documents…')).toBeNull()
  })
  await user.type(box, question)
  await user.keyboard('{Enter}')
  return user
}

/** A stream that sends `text` as one delta, then waits until it is aborted. */
function streamUntilAborted(text: string) {
  mocks.stream.mockImplementation(({ onEvent, signal }: StreamMessageOptions) => {
    onEvent({ type: 'delta', text })
    return new Promise<void>((resolve) => {
      signal?.addEventListener('abort', () => {
        resolve()
      })
    })
  })
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.config.mockResolvedValue({ max_upload_mb: 20, max_question_chars: 4000 })
  mocks.documents.mockResolvedValue([makeDocument({ status: 'ready' })])
  mocks.conversations.mockResolvedValue([])
  mocks.messages.mockResolvedValue([])
})

describe('ChatPanel', () => {
  it('shows saved messages, with refused, uncited and stopped answers labelled', async () => {
    mocks.messages.mockResolvedValue([
      makeMessage({ id: 'q1', role: 'user', content: 'Do you do braces?', citations: [] }),
      makeMessage({
        id: 'a1',
        content: "I couldn't find that in the documents.",
        citations: [],
        refused: true,
      }),
      makeMessage({ id: 'q2', role: 'user', content: 'Hours?', citations: [] }),
      makeMessage({ id: 'a2', content: 'Probably 9 to 5.', citations: [], uncited: true }),
      makeMessage({ id: 'q3', role: 'user', content: 'Prices?', citations: [] }),
      makeMessage({ id: 'a3', content: 'A cleaning costs', citations: [], incomplete: true }),
    ])
    renderPanel()

    expect(await screen.findByText('Do you do braces?')).toBeTruthy()
    expect(screen.getByText('Not found in your documents')).toBeTruthy()
    expect(screen.getByText(/No sources cited/)).toBeTruthy()
    expect(screen.getByText('Stopped')).toBeTruthy()
  })

  it('lists the cited sources under an answer', async () => {
    mocks.messages.mockResolvedValue([makeMessage()])
    renderPanel()

    const sources = await screen.findByRole('list', { name: 'Sources' })
    expect(sources.textContent).toContain('faq.txt · lines 3–8')
  })

  it('numbers a saved answer’s citations 1, 2 in order of first use, in the text and the list', async () => {
    mocks.messages.mockResolvedValue([
      makeMessage({
        content: 'Cards are accepted [3]. We open at 9 [1].',
        citations: [
          makeCitation({ number: 1, filename: 'hours.txt', label: 'line 1' }),
          makeCitation({ number: 3, filename: 'payments.txt', label: 'line 7' }),
        ],
      }),
    ])
    renderPanel()

    expect(
      await screen.findByRole('button', { name: 'Source 1: payments.txt, line 7' }),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Source 2: hours.txt, line 1' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Source 3/ })).toBeNull()
    const items = within(screen.getByRole('list', { name: 'Sources' })).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      'payments.txt · line 71',
      'hours.txt · line 12',
    ])
  })

  it('previews a citation from saved history, with the original from this workspace', async () => {
    mocks.messages.mockResolvedValue([makeMessage()])
    mocks.fileText.mockResolvedValue('')
    mocks.fileExists.mockResolvedValue(true)
    renderPanel()

    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Source 1: faq\.txt/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('We are open Monday to Friday, 9am to 5pm.')).toBeTruthy()
    expect(await within(dialog).findByRole('button', { name: /open original/i })).toBeTruthy()
    expect(mocks.fileExists).toHaveBeenCalledWith('ws1', 'd1')
  })

  it('explains why sending is disabled while documents are indexing', async () => {
    mocks.documents.mockResolvedValue([makeDocument({ status: 'processing' })])
    renderPanel()

    expect(await screen.findByText(/still being indexed/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Send' }).hasAttribute('disabled')).toBe(true)
  })

  it('streams an answer live and can stop it', async () => {
    streamUntilAborted('We are open')
    renderPanel()

    const user = await ask('When are you open?')

    expect(await screen.findByText('We are open')).toBeTruthy()
    expect(screen.getByText('When are you open?')).toBeTruthy()
    expect(mocks.stream).toHaveBeenCalledWith(
      expect.objectContaining({ conversationId: 'c1', question: 'When are you open?' }),
    )
    await user.click(screen.getByRole('button', { name: 'Stop' }))

    expect(await screen.findByText('Stopped')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Send' })).toBeTruthy()
  })

  it('starts a conversation with the first question', async () => {
    mocks.create.mockResolvedValue({
      id: 'c9',
      workspace_id: 'ws1',
      title: '',
      created_at: '2026-01-01T00:00:00Z',
    })
    mocks.stream.mockResolvedValue(undefined)
    renderPanel('/w/ws1')

    await ask('When are you open?')

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/w/ws1/c/c9')
    })
    expect(mocks.create).toHaveBeenCalledWith('ws1')
    expect(mocks.stream).toHaveBeenCalledWith(expect.objectContaining({ conversationId: 'c9' }))
  })

  it('offers starter questions in a new chat and asks one when clicked', async () => {
    mocks.create.mockResolvedValue({
      id: 'c9',
      workspace_id: 'ws1',
      title: '',
      created_at: '2026-01-01T00:00:00Z',
    })
    mocks.stream.mockResolvedValue(undefined)
    renderPanel('/w/ws1', STARTERS)

    const starters = await screen.findByRole('list', { name: 'Suggested questions' })
    expect(starters.textContent).toContain('Is there parking?')
    const chip = screen.getByRole('button', { name: 'What are your opening hours?' })
    await waitFor(() => {
      expect(chip.hasAttribute('disabled')).toBe(false)
    })
    await userEvent.setup().click(chip)

    await waitFor(() => {
      expect(mocks.stream).toHaveBeenCalledWith(
        expect.objectContaining({ conversationId: 'c9', question: 'What are your opening hours?' }),
      )
    })
  })

  it('shows no starter questions when the workspace has none', async () => {
    renderPanel('/w/ws1')

    expect(await screen.findByText('Ask about your documents')).toBeTruthy()
    expect(screen.queryByRole('list', { name: 'Suggested questions' })).toBeNull()
  })

  it('disables the starter questions until a document is ready', async () => {
    mocks.documents.mockResolvedValue([makeDocument({ status: 'processing' })])
    renderPanel('/w/ws1', STARTERS)

    expect(await screen.findByText(/still being indexed/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Is there parking?' }).hasAttribute('disabled')).toBe(
      true,
    )
  })

  it('shows an error with a Retry that asks again', async () => {
    mocks.stream.mockImplementationOnce(({ onEvent }: StreamMessageOptions) => {
      onEvent({ type: 'error', message: 'The AI service is busy. Please try again.' })
      return Promise.resolve()
    })
    mocks.stream.mockResolvedValue(undefined)
    renderPanel()

    const user = await ask('When are you open?')
    expect(await screen.findByText('The AI service is busy. Please try again.')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(mocks.stream).toHaveBeenCalledTimes(2)
    })
    expect(mocks.stream.mock.calls[1]?.[0]).toMatchObject({ question: 'When are you open?' })
  })

  it('shows the message when a reply is already in progress', async () => {
    mocks.stream.mockRejectedValue(
      new ApiError(409, 'A reply is already being written in this conversation.'),
    )
    renderPanel()

    await ask('Hello?')

    expect(
      await screen.findByText('A reply is already being written in this conversation.'),
    ).toBeTruthy()
  })

  it("won't send a question over the server's limit", async () => {
    mocks.config.mockResolvedValue({ max_upload_mb: 20, max_question_chars: 10 })
    renderPanel()

    const box = await screen.findByRole('textbox', { name: 'Ask a question' })
    await userEvent.setup().type(box, 'This is far too long')

    expect(await screen.findByText(/up to 10 characters/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Send' }).hasAttribute('disabled')).toBe(true)
  })

  it('says so when the conversation does not exist', async () => {
    mocks.messages.mockRejectedValue(new ApiError(404, 'Conversation not found'))
    renderPanel('/w/ws1/c/missing')

    expect(await screen.findByText('Conversation not found')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Start a new chat' }).getAttribute('href')).toBe(
      '/w/ws1',
    )
  })
  it('turns the chat area into an upload area when the workspace has no documents', async () => {
    mocks.documents.mockResolvedValue([])
    renderPanel('/w/ws1')

    expect(
      await screen.findByRole('heading', { name: 'Add documents to get started' }),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: /drop files here/i })).toBeTruthy()
  })

  it('opens the conversations and documents in sheets on narrow screens', async () => {
    setMatchMedia(false)
    mocks.conversations.mockResolvedValue([
      { id: 'c2', workspace_id: 'ws1', title: 'Is there parking?', created_at: '2026-01-01' },
    ])
    renderWithProviders(
      <ChatPanel workspaceId="ws1" documentsPanel={<p>The documents panel</p>} />,
      '/w/ws1',
    )
    const user = userEvent.setup()

    // Neither list takes room beside the chat
    expect(screen.queryByRole('navigation', { name: 'Conversations' })).toBeNull()

    await user.click(screen.getByRole('button', { name: /documents/i }))
    const documents = await screen.findByRole('dialog', { name: 'Documents' })
    expect(within(documents).getByText('The documents panel')).toBeTruthy()
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })

    await user.click(screen.getByRole('button', { name: 'Chats' }))
    const chats = await screen.findByRole('dialog', { name: 'Chats' })
    await user.click(await within(chats).findByRole('link', { name: /Is there parking\?/ }))

    // Picking a conversation opens it and closes the sheet
    expect(screen.getByTestId('location').textContent).toBe('/w/ws1/c/c2')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
  })
})
