import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'group inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full border border-transparent text-sm font-medium tracking-[-0.015em] transition-[transform,background-color,border-color,color,box-shadow] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] active:translate-y-px active:scale-[0.985] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'bg-[var(--primary)] text-[var(--primary-foreground)] shadow-[var(--shadow-button)] hover:-translate-y-px hover:bg-[var(--primary-strong)]',
        outline:
          'border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_72%,transparent)] text-[var(--foreground)] shadow-[0_12px_26px_rgba(18,24,36,0.05)] hover:-translate-y-px hover:border-[var(--line-strong)] hover:bg-[color-mix(in_srgb,var(--surface)_92%,white)]',
        ghost:
          'border-transparent bg-transparent text-[var(--foreground-soft)] hover:bg-[color-mix(in_srgb,var(--foreground)_4%,transparent)] hover:text-[var(--foreground)]',
        link:
          'h-auto rounded-none border-none bg-transparent px-0 py-0 text-[var(--primary)] shadow-none hover:text-[var(--primary-strong)] hover:underline hover:underline-offset-4',
      },
      size: {
        xs: 'h-8 px-2.5 text-xs',
        default: 'h-11 px-4 py-2.5',
        sm: 'h-9 px-3.5 text-xs',
        lg: 'h-12 px-6 text-sm',
        icon: 'h-10 w-10',
        'icon-xs': 'h-7 w-7',
        'icon-sm': 'h-8 w-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

export { Button }
