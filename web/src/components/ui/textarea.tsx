import * as React from 'react'

import { cn } from '@/lib/utils'

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<'textarea'>
>(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        'flex min-h-[96px] w-full rounded-[var(--radius-control)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_76%,transparent)] px-4 py-3 text-sm leading-6 text-[var(--foreground)] shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] placeholder:text-[var(--muted-foreground)] transition-[border-color,box-shadow,background-color] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] focus-visible:border-[color-mix(in_srgb,var(--primary)_38%,var(--line))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--primary)_18%,transparent)] disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      ref={ref}
      {...props}
    />
  )
})
Textarea.displayName = 'Textarea'

export { Textarea }
