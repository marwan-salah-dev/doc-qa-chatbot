import 'react-pdf/dist/Page/TextLayer.css'

import { useCallback, useEffect, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'

import { highlightTextItem } from '@/lib/citationPreview'

// Must be set in the module that renders react-pdf (see its README); Vite bundles the worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

interface PdfPagesProps {
  url: string
  /** The cited pages, in order */
  pages: number[]
  /** The cited passage; text runs on the page that belong to it are highlighted */
  passage: string
}

/** The cited pages of a PDF, fitted to the panel's width, with the passage highlighted.
 * Loaded lazily: pdf.js is large and only needed once someone opens a PDF citation. */
export default function PdfPages({ url, pages, passage }: PdfPagesProps) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null)
  const width = useWidth(container)
  const renderText = useCallback(
    ({ str }: { str: string }) => highlightTextItem(str, passage),
    [passage],
  )

  return (
    <div ref={setContainer} className="pdf-pages grid min-w-0 gap-3">
      <Document
        file={url}
        // react-pdf 11 throws load errors to Suspense/error boundaries by default; this keeps
        // them in the `loading` and `error` props below
        suspense={false}
        loading={<p className="text-sm text-muted-foreground">Loading the PDF…</p>}
        error={
          <p className="text-sm text-muted-foreground">
            Couldn&apos;t load the original file. The cited passage is shown below.
          </p>
        }
      >
        {width > 0 &&
          pages.map((page) => (
            <figure key={page} className="grid gap-1">
              <Page
                pageNumber={page}
                width={width}
                renderAnnotationLayer={false}
                customTextRenderer={renderText}
                className="overflow-hidden rounded-md border bg-white shadow-xs"
                loading={<div className="aspect-[1/1.3] animate-pulse rounded-md bg-muted" />}
                error={
                  <p className="text-sm text-destructive">Page {page} couldn&apos;t be shown.</p>
                }
              />
              <figcaption className="text-center text-xs text-muted-foreground">
                Page {page}
              </figcaption>
            </figure>
          ))}
      </Document>
    </div>
  )
}

/** The element's content width, kept up to date as the panel resizes. */
function useWidth(element: HTMLElement | null): number {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width))
    })
    observer.observe(element)
    return () => {
      observer.disconnect()
    }
  }, [element])
  return width
}
