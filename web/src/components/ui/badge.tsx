import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-medium tracking-[0.14em] uppercase transition-[background-color,border-color,color,transform] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]',
  {
    variants: {
      variant: {
        default:
          'border-[color-mix(in_srgb,var(--primary)_18%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_9%,white)] text-[var(--foreground)]',
        outline:
          'border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_72%,transparent)] text-[var(--muted-foreground)]',
        source:
          'border-transparent bg-[color-mix(in_srgb,var(--foreground)_6%,transparent)] text-[var(--foreground-soft)]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge }
