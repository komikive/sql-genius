import * as React from 'react'
import { CaretDown } from '@phosphor-icons/react'

import { cn } from '@/lib/utils'

const Select = React.forwardRef<HTMLSelectElement, React.ComponentProps<'select'>>(
  ({ className, children, ...props }, ref) => {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={cn(
            'flex h-11 w-full appearance-none rounded-[var(--radius-control)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_76%,transparent)] px-4 pr-11 text-sm text-[var(--foreground)] shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] transition-[border-color,box-shadow,background-color] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] focus-visible:border-[color-mix(in_srgb,var(--primary)_38%,var(--line))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--primary)_18%,transparent)] disabled:cursor-not-allowed disabled:opacity-50',
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <CaretDown className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
      </div>
    )
  },
)

Select.displayName = 'Select'

const SelectTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement>
>(({ className, children, type = 'button', ...props }, ref) => (
  <button
    ref={ref}
    type={type}
    className={cn(
      'inline-flex h-9 items-center gap-2 rounded-full border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_76%,transparent)] px-3 text-sm text-[var(--foreground)] shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] transition-[border-color,box-shadow,background-color] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--primary)_18%,transparent)]',
      className,
    )}
    {...props}
  >
    {children}
  </button>
))

SelectTrigger.displayName = 'SelectTrigger'

const SelectContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'rounded-[var(--radius-card)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_90%,white)] p-1 shadow-[var(--shadow-card)]',
        className,
      )}
      {...props}
    />
  ),
)

SelectContent.displayName = 'SelectContent'

const SelectItem = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      role="option"
      className={cn(
        'rounded-[calc(var(--radius-control)-0.25rem)] px-3 py-2 text-sm text-[var(--foreground)]',
        className,
      )}
      {...props}
    />
  ),
)

SelectItem.displayName = 'SelectItem'

const SelectValue = React.forwardRef<HTMLSpanElement, React.HTMLAttributes<HTMLSpanElement>>(
  ({ className, ...props }, ref) => (
    <span ref={ref} className={cn('truncate', className)} {...props} />
  ),
)

SelectValue.displayName = 'SelectValue'

export { Select, SelectContent, SelectItem, SelectTrigger, SelectValue }
