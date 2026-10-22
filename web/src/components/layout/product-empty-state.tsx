import type { ReactNode } from 'react'
import type { Icon } from '@phosphor-icons/react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type ProductEmptyStateProps = {
  icon: Icon
  title: string
  description: string
  action?: ReactNode
  className?: string
}

export function ProductEmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: ProductEmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-[1.7rem] border border-dashed border-[color-mix(in_srgb,var(--line-strong)_44%,var(--line))] bg-[rgba(255,255,255,0.48)] px-6 py-14 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] backdrop-blur-xl',
        className,
      )}
    >
      <span className="flex size-12 items-center justify-center rounded-2xl border border-white/70 bg-[color-mix(in_srgb,var(--primary)_9%,white)] text-[var(--primary)] shadow-[0_12px_28px_rgba(36,88,211,0.08)]">
        <Icon className="size-5" weight="duotone" />
      </span>
      <div className="mt-4 space-y-1">
        <p className="text-sm font-semibold tracking-[-0.02em] text-[var(--foreground)]">{title}</p>
        <p className="max-w-[38ch] text-xs leading-5 text-[var(--foreground-soft)]">{description}</p>
      </div>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}

export function ProductEmptyAction({
  children,
  onClick,
}: {
  children: ReactNode
  onClick?: () => void
}) {
  return (
    <Button size="sm" onClick={onClick}>
      {children}
    </Button>
  )
}
