import { SpinnerGap } from '@phosphor-icons/react'

import { cn } from '@/lib/utils'

function Spinner({ className, ...props }: React.ComponentProps<'svg'>) {
  return (
    <SpinnerGap
      aria-label="Loading"
      className={cn('size-4 animate-spin text-current', className)}
      role="status"
      {...props}
    />
  )
}

export { Spinner }
