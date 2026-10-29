import { FileIcon, FileTextIcon, FileTypeIcon as FileWordIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

const STYLES = {
  pdf: { Icon: FileTextIcon, tile: 'bg-[#e5484d]/10 text-[#e5484d]' },
  docx: { Icon: FileWordIcon, tile: 'bg-[#3e63dd]/10 text-[#3e63dd] dark:text-[#849dff]' },
  txt: { Icon: FileIcon, tile: 'bg-muted text-muted-foreground' },
}

function kindOf(filename: string): keyof typeof STYLES {
  const extension = filename.slice(filename.lastIndexOf('.') + 1).toLowerCase()
  return extension === 'pdf' || extension === 'docx' ? extension : 'txt'
}

/** A small tinted tile with the file's type, so PDFs, DOCX and TXT files are told apart at a glance. */
export function FileTypeIcon({ filename, className }: { filename: string; className?: string }) {
  const { Icon, tile } = STYLES[kindOf(filename)]
  return (
    <span
      aria-hidden
      className={cn('grid size-8 shrink-0 place-items-center rounded-md', tile, className)}
    >
      <Icon className="size-4" />
    </span>
  )
}
