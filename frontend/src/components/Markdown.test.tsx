// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { makeCitation } from '@/test/render'

import { Markdown } from './Markdown'

const citation = makeCitation()

describe('Markdown', () => {
  it('renders GitHub-flavoured markdown such as tables', () => {
    render(<Markdown text={'| Service | Price |\n| --- | --- |\n| Cleaning | $80 |'} />)

    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByRole('cell', { name: '$80' })).toBeTruthy()
  })

  it('shows raw HTML as text instead of rendering it', () => {
    const { container } = render(<Markdown text={'<script>alert(1)</script> <b>bold</b>'} />)

    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })

  it('turns citation markers into chips that show the cited text', async () => {
    render(<Markdown text="We are open 9 to 5 [1]." citations={[citation]} />)

    const chip = screen.getByRole('button', { name: 'Source 1: faq.txt, lines 3–8' })
    expect(chip.textContent).toBe('1')
    await userEvent.setup().click(chip)

    expect(await screen.findByText('We are open Monday to Friday, 9am to 5pm.')).toBeTruthy()
  })

  it('leaves markers inside code alone', () => {
    render(<Markdown text="Write `[1]` to cite." citations={[citation]} />)

    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('[1]').tagName).toBe('CODE')
  })

  it('leaves markers without a matching source as text', () => {
    render(<Markdown text="See [4]." citations={[citation]} />)

    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('See [4].')).toBeTruthy()
  })

  it('opens ordinary links in a new tab', () => {
    render(<Markdown text="[Book online](https://example.com/book)" />)

    const link = screen.getByRole('link', { name: 'Book online' })
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  })
})
