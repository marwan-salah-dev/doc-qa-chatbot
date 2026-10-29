import { LoaderCircleIcon, UploadIcon, XIcon } from 'lucide-react'
import { type DragEvent, useRef, useState } from 'react'

import { useConfig, useUploadDocument } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { describeUploadError } from '@/lib/uploadErrors'
import { ACCEPTED_EXTENSIONS, validateFile } from '@/lib/uploadValidation'
import { cn } from '@/lib/utils'

/** A file that is waiting, being uploaded, or was turned away. Uploaded files leave this list:
 * the document list below shows them from then on. */
interface UploadItem {
  id: number
  name: string
  state: 'waiting' | 'uploading' | 'error'
  title?: string
  message?: string
}

/** Drag-and-drop zone and file picker. Files are checked in the browser first, then uploaded one
 * at a time in the order given (a later drop queues behind an earlier one). */
export function DocumentUploader({ workspaceId }: { workspaceId: string }) {
  const config = useConfig()
  const upload = useUploadDocument(workspaceId)
  const maxUploadMb = config.data?.max_upload_mb
  const inputRef = useRef<HTMLInputElement>(null)
  const nextId = useRef(0)
  const queue = useRef<Promise<void>>(Promise.resolve())
  const [dragging, setDragging] = useState(false)
  const [items, setItems] = useState<UploadItem[]>([])

  function patchItem(id: number, patch: Partial<UploadItem>) {
    setItems((all) => all.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }

  function dropItem(id: number) {
    setItems((all) => all.filter((item) => item.id !== id))
  }

  async function uploadOne(id: number, file: File) {
    patchItem(id, { state: 'uploading' })
    try {
      await upload.mutateAsync(file)
      dropItem(id)
    } catch (error) {
      patchItem(id, { state: 'error', ...describeUploadError(error, maxUploadMb) })
    }
  }

  function handleFiles(files: File[]) {
    const accepted: { id: number; file: File }[] = []
    const added: UploadItem[] = []
    for (const file of files) {
      const id = nextId.current++
      const problem = validateFile(file, maxUploadMb)
      if (problem) {
        added.push({ id, name: file.name, state: 'error', title: 'Not uploaded', message: problem })
      } else {
        added.push({ id, name: file.name, state: 'waiting' })
        accepted.push({ id, file })
      }
    }
    if (added.length === 0) return
    setItems((all) => [...all, ...added])
    queue.current = queue.current.then(async () => {
      for (const { id, file } of accepted) await uploadOne(id, file)
    })
  }

  function handleDragOver(event: DragEvent<HTMLElement>) {
    event.preventDefault() // without this the browser never allows a drop
    setDragging(true)
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault()
    setDragging(false)
    handleFiles(Array.from(event.dataTransfer.files))
  }

  return (
    <div className="grid gap-3">
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS.join(',')}
        className="sr-only"
        tabIndex={-1}
        aria-label="Choose files"
        onChange={(event) => {
          handleFiles(Array.from(event.target.files ?? []))
          event.target.value = '' // so picking the same file again still fires onChange
        }}
      />
      <button
        type="button"
        data-dragging={dragging}
        onClick={() => inputRef.current?.click()}
        onDragEnter={handleDragOver}
        onDragOver={handleDragOver}
        onDragLeave={() => {
          setDragging(false)
        }}
        onDrop={handleDrop}
        className={cn(
          'flex flex-col items-center gap-1 rounded-lg border border-dashed px-4 py-6 text-center transition-colors hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
          'data-[dragging=true]:border-primary data-[dragging=true]:bg-primary/5',
        )}
      >
        <UploadIcon className="pointer-events-none size-5 text-muted-foreground" aria-hidden />
        <span className="pointer-events-none text-sm font-medium">
          Drop files here or click to choose
        </span>
        <span className="pointer-events-none text-xs text-muted-foreground">
          {maxUploadMb === undefined
            ? 'PDF, DOCX or TXT'
            : `PDF, DOCX or TXT · up to ${String(maxUploadMb)} MB each`}
        </span>
      </button>

      {items.length > 0 && (
        <ul aria-label="Uploads" aria-live="polite" className="grid gap-2">
          {items.map((item) => (
            <li key={item.id} className="flex items-start gap-2 rounded-md border p-2 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium" title={item.name}>
                  {item.name}
                </p>
                {item.state === 'waiting' && <p className="text-muted-foreground">Waiting…</p>}
                {item.state === 'uploading' && (
                  <p className="flex items-center gap-1 text-muted-foreground">
                    <LoaderCircleIcon className="size-3.5 animate-spin" aria-hidden />
                    Uploading…
                  </p>
                )}
                {item.state === 'error' && (
                  <p className="text-destructive">
                    <span className="font-medium">{item.title}</span>
                    <br />
                    <span>{item.message}</span>
                  </p>
                )}
              </div>
              {item.state === 'error' && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Dismiss ${item.name}`}
                  onClick={() => {
                    dropItem(item.id)
                  }}
                >
                  <XIcon />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
