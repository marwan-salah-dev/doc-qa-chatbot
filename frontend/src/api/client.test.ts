import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api } from './client'

function mockFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('sends the visitor id with every request', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(Response.json([])))
    vi.stubGlobal('fetch', fetchMock)

    await api.workspaces.list()
    await api.documents.list('w1')

    const ids = (fetchMock.mock.calls as unknown as [string, RequestInit][]).map(([, init]) =>
      new Headers(init.headers).get('X-Visitor-Id'),
    )
    expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/)
    expect(ids[1]).toBe(ids[0])
  })

  it('fetches an original file as a blob, with the visitor id', async () => {
    const fetchMock = mockFetch(
      new Response('hello', { headers: { 'Content-Type': 'text/plain' } }),
    )

    const blob = await api.documents.fileBlob('w1', 'd1')

    expect(await blob.text()).toBe('hello')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/workspaces/w1/documents/d1/file')
    expect(new Headers(init.headers).get('X-Visitor-Id')).toBeTruthy()
  })

  it('throws the server message when the original file cannot be fetched', async () => {
    mockFetch(Response.json({ detail: 'Document not found' }, { status: 404 }))

    await expect(api.documents.fileBlob('w1', 'd1')).rejects.toMatchObject({
      message: 'Document not found',
    })
  })

  it('returns parsed JSON and calls the proxied path', async () => {
    const workspaces = [{ id: 'w1', name: 'Acme Dental', created_at: '2026-10-29T10:00:00Z' }]
    const fetchMock = mockFetch(Response.json(workspaces))

    expect(await api.workspaces.list()).toEqual(workspaces)
    expect(fetchMock).toHaveBeenCalledWith('/api/workspaces', expect.anything())
  })

  it('sends JSON bodies', async () => {
    const fetchMock = mockFetch(
      Response.json(
        { id: 'w1', name: 'Acme', created_at: '2026-10-29T10:00:00Z' },
        { status: 201 },
      ),
    )

    await api.workspaces.create('Acme')
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"name":"Acme"}')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('returns undefined for 204 No Content', async () => {
    mockFetch(new Response(null, { status: 204 }))

    await expect(api.workspaces.remove('w1')).resolves.toBeUndefined()
  })

  it('uses a string detail as the error message', async () => {
    mockFetch(Response.json({ detail: 'Workspace not found' }, { status: 404 }))

    await expect(api.workspaces.get('nope')).rejects.toMatchObject({
      status: 404,
      message: 'Workspace not found',
    })
  })

  it('uses the first validation message from a 422', async () => {
    mockFetch(
      Response.json(
        {
          detail: [
            {
              type: 'value_error',
              loc: ['body', 'name'],
              msg: 'Value error, name must not be blank',
            },
          ],
        },
        { status: 422 },
      ),
    )

    const error = await api.workspaces.create(' ').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 422, message: 'Value error, name must not be blank' })
  })

  it('falls back to a generic message when the body is not JSON', async () => {
    mockFetch(new Response('Bad gateway', { status: 502 }))

    await expect(api.workspaces.list()).rejects.toMatchObject({
      status: 502,
      message: 'Something went wrong (502). Please try again.',
    })
  })

  it('uploads documents as multipart with the "file" field and no JSON header', async () => {
    const fetchMock = mockFetch(Response.json({ id: 'd1' }, { status: 202 }))
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })

    await api.documents.upload('w1', file)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/workspaces/w1/documents')
    expect((init.body as FormData).get('file')).toBeInstanceOf(File)
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
  })

  it('checks the original file with HEAD', async () => {
    const fetchMock = mockFetch(new Response(null, { status: 200 }))

    expect(await api.documents.fileExists('ws1', 'd1')).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/workspaces/ws1/documents/d1/file', {
      method: 'HEAD',
      headers: { 'X-Visitor-Id': expect.any(String) as string },
    })
  })

  it('reports a missing original file as not existing', async () => {
    mockFetch(new Response(null, { status: 404 }))

    expect(await api.documents.fileExists('ws1', 'd1')).toBe(false)
  })
})
