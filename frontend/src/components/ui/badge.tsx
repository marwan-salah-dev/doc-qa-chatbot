import { cva, type VariantProps } from 'class-variance-authority'
import type * as React from 'react'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1 rounded-full border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap [&_svg:not([class*='size-'])]:size-3",
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground',
        soft: 'bg-primary-soft text-primary-soft-foreground',
        secondary: 'bg-secondary text-secondary-foreground',
        outline: 'border-border text-foreground',
        success: 'bg-success/10 text-success dark:bg-success/15',
        warning:
          'bg-warning/12 text-[color-mix(in_oklab,var(--warning),black_25%)] dark:bg-warning/15 dark:text-warning',
        destructive: 'bg-destructive/10 text-destructive dark:bg-destructive/20',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge }
