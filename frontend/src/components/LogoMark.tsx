import { useId } from 'react'

import { cn } from '@/lib/utils'

/** The DocQA mark: a page with a citation dot on an iris tile. Same drawing as public/favicon.svg. */
export function LogoMark({ className }: { className?: string }) {
  // Two marks on a page (header and an answer avatar) need their own gradient ids
  const gradient = useId()
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={cn('size-6 shrink-0', className)}>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop stopColor="#7a78f0" />
          <stop offset="1" stopColor="#4b4acf" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill={`url(#${gradient})`} />
      <path
        d="M7.5 5.5h6.25L17 8.75V17.5a1 1 0 0 1-1 1H7.5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z"
        fill="#fff"
      />
      <path d="M13.75 5.5V8a.75.75 0 0 0 .75.75H17" fill="#c9c8fb" />
      <path
        d="M9 11h5.5M9 13.5h5.5M9 16h2.5"
        stroke="#5b5bd6"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <circle cx="14" cy="16" r="1.1" fill="#5b5bd6" />
    </svg>
  )
}
