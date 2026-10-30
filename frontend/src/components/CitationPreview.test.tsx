// @vitest-environment jsdom
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { CitationChip } from '@/components/CitationChip'
import { CitationPreviewProvider } from '@/components/CitationPreview'
import { makeCitation, renderWithProviders } from '@/test/render'

const mocks = vi.hoisted(() => ({
  fileText: vi.fn(),
  fileExists: vi.fn(),
  fileBlob: vi.fn(),
  toastError: vi.fn(),
  pdfFails: false,
}))

vi.mock('sonner', () => ({ toast: { error: mocks.toastError } }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      documents: {
        ...actual.api.documents,
        fileText: mocks.fileText,
        fileExists: mocks.fileExists,
        fileBlob: mocks.fileBlob,
      },
    },
  }
})

// pdf.js can't run in jsdom; the real viewer is checked in the browser
vi.mock('@/components/PdfPages', () => ({
  default: ({ url, pages }: { url: string; pages: number[] }) => {
    if (mocks.pdfFails) throw new Error('Unexpected server response (404) while retrieving PDF')
    return (
      <div data-testid="pdf-pages">
        {url} pages {pages.join(',')}
      </div>
    )
  },
}))

function renderChip(citation = makeCitation()) {
  renderWithProviders(
    <CitationPreviewProvider workspaceId="ws1">
      <CitationChip citation={citation} variant="source" />
    </CitationPreviewProvider>,
  )
}

async function openPreview(name = /faq\.txt/) {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name }))
  return { user, dialog: await screen.findByRole('dialog') }
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.fileExists.mockResolvedValue(true)
  mocks.pdfFails = false
})

describe('citation preview', () => {
  it('shows the file, its location and the cited passage', async () => {
    mocks.fileText.mockResolvedValue('')
    renderChip()
    const { dialog } = await openPreview()

    expect(within(dialog).getByRole('heading', { name: 'faq.txt' })).toBeTruthy()
    expect(within(dialog).getByText('lines 3–8')).toBeTruthy()
    expect(within(dialog).getByText('We are open Monday to Friday, 9am to 5pm.')).toBeTruthy()
    expect(await within(dialog).findByRole('button', { name: /open original/i })).toBeTruthy()
    expect(mocks.fileExists).toHaveBeenCalledWith('ws1', 'd1')
  })

  it('hides "Open original" when the file is gone', async () => {
    mocks.fileText.mockResolvedValue('')
    mocks.fileExists.mockResolvedValue(false)
    renderChip()
    const { dialog } = await openPreview()

    await vi.waitFor(() => {
      expect(mocks.fileExists).toHaveBeenCalled()
    })
    // Let the answer reach the component before checking that nothing appeared
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(within(dialog).queryByRole('button', { name: /open original/i })).toBeNull()
  })

  it('hides "Open original" until the file is known to exist', async () => {
    mocks.fileText.mockResolvedValue('')
    mocks.fileExists.mockReturnValue(new Promise(() => undefined))
    renderChip()
    const { dialog } = await openPreview()

    expect(within(dialog).queryByRole('button', { name: /open original/i })).toBeNull()
  })

  describe('"Open original"', () => {
    // A plain link can't send the X-Visitor-Id header, so the file is fetched as a blob. The tab
    // is opened before that fetch, while the click still counts, so popup blockers allow it.
    function fakeTab() {
      return { opener: {} as unknown, location: { href: '' }, close: vi.fn() }
    }

    beforeEach(() => {
      vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:file') }))
    })

    afterEach(() => {
      vi.unstubAllGlobals()
    })

    async function clickOpen() {
      mocks.fileText.mockResolvedValue('')
      renderChip()
      const { user, dialog } = await openPreview()
      await user.click(await within(dialog).findByRole('button', { name: /open original/i }))
      return dialog
    }

    it('opens a tab at once, then points it at the fetched file', async () => {
      const tab = fakeTab()
      const open = vi.fn(() => tab)
      vi.stubGlobal('open', open)
      mocks.fileBlob.mockResolvedValue(new Blob(['x']))

      await clickOpen()

      expect(open).toHaveBeenCalledWith('', '_blank')
      await vi.waitFor(() => {
        expect(tab.location.href).toBe('blob:file')
      })
      expect(tab.opener).toBeNull()
      expect(mocks.fileBlob).toHaveBeenCalledWith('ws1', 'd1')
    })

    it('closes the tab and says why when the file cannot be fetched', async () => {
      const tab = fakeTab()
      vi.stubGlobal(
        'open',
        vi.fn(() => tab),
      )
      mocks.fileBlob.mockRejectedValue(new ApiError(404, 'Document not found'))

      const dialog = await clickOpen()

      await vi.waitFor(() => {
        expect(tab.close).toHaveBeenCalled()
      })
      expect(within(dialog).getByRole('alert').textContent).toContain('Document not found')
      expect(mocks.toastError).toHaveBeenCalled()
    })

    it('downloads the file instead when the tab is blocked', async () => {
      vi.stubGlobal(
        'open',
        vi.fn(() => null),
      )
      mocks.fileBlob.mockResolvedValue(new Blob(['x']))
      const click = vi
        .spyOn(HTMLAnchorElement.prototype, 'click')
        .mockImplementation(() => undefined)

      await clickOpen()

      await vi.waitFor(() => {
        expect(click).toHaveBeenCalled()
      })
      const anchor = click.mock.contexts[0] as HTMLAnchorElement
      expect(anchor.download).toBe('faq.txt')
      expect(anchor.href).toBe('blob:file')
    })
  })

  it('opens a PDF at the cited pages', async () => {
    renderChip(
      makeCitation({
        filename: 'handbook.pdf',
        location: { kind: 'pdf', page: 2, page_end: 3 },
        label: 'pages 2-3',
      }),
    )
    const { dialog } = await openPreview(/handbook\.pdf/)

    expect((await within(dialog).findByTestId('pdf-pages')).textContent).toBe(
      '/api/workspaces/ws1/documents/d1/file pages 2,3',
    )
    expect(mocks.fileText).not.toHaveBeenCalled()
  })

  it('keeps the passage, and the app, when the PDF viewer fails', async () => {
    mocks.pdfFails = true
    vi.spyOn(console, 'error').mockImplementation(() => undefined) // React logs caught errors
    renderChip(
      makeCitation({
        filename: 'handbook.pdf',
        location: { kind: 'pdf', page: 1 },
        label: 'page 1',
      }),
    )
    const { dialog } = await openPreview(/handbook\.pdf/)

    expect(await within(dialog).findByText(/couldn't load the original file/i)).toBeTruthy()
    expect(within(dialog).getByText('We are open Monday to Friday, 9am to 5pm.')).toBeTruthy()
  })

  it('shows a TXT passage among the lines around it, with line numbers', async () => {
    mocks.fileText.mockResolvedValue('a\nb\nc\nd\ne\nf\ng\nh\ni\nj\nk\nl\nm')
    renderChip(makeCitation({ location: { kind: 'txt', start: 6, end: 7 }, label: 'lines 6-7' }))
    const { dialog } = await openPreview()

    const context = await within(dialog).findByRole('list', { name: 'Lines around the passage' })
    const lines = within(context).getAllByRole('listitem')
    expect(lines.map((l) => l.textContent)).toEqual([
      '3c',
      '4d',
      '5e',
      '6f',
      '7g',
      '8h',
      '9i',
      '10j',
    ])
    expect(lines.filter((l) => l.dataset.cited === 'true').map((l) => l.textContent)).toEqual([
      '6f',
      '7g',
    ])
    expect(mocks.fileText).toHaveBeenCalledWith('ws1', 'd1')
    // The highlighted lines are the passage, so it isn't repeated as a quote
    expect(within(dialog).queryByText('We are open Monday to Friday, 9am to 5pm.')).toBeNull()
  })

  it('still shows the passage when the original file is gone', async () => {
    mocks.fileText.mockRejectedValue(new ApiError(404, 'The original file is missing'))
    renderChip()
    const { dialog } = await openPreview()

    expect(await within(dialog).findByText(/couldn't load the original file/i)).toBeTruthy()
    expect(within(dialog).getByText('We are open Monday to Friday, 9am to 5pm.')).toBeTruthy()
  })

  it('shows the heading a DOCX passage sits under', async () => {
    renderChip(
      makeCitation({
        filename: 'prices.docx',
        location: { kind: 'docx', heading: 'Implants', start: 4, end: 6 },
        label: 'Implants · paragraphs 4-6',
      }),
    )
    const { dialog } = await openPreview(/prices\.docx/)

    expect(within(dialog).getByText('Implants')).toBeTruthy()
    expect(within(dialog).getByText('Paragraphs 4–6')).toBeTruthy()
    expect(mocks.fileText).not.toHaveBeenCalled()
  })

  it('closes with the close button', async () => {
    mocks.fileText.mockResolvedValue('')
    renderChip()
    const { user, dialog } = await openPreview()

    await user.click(within(dialog).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
