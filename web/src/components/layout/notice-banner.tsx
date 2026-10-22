import type { ReactNode } from 'react'
import { WarningCircle, CheckCircle } from '@phosphor-icons/react'

import { cn } from '@/lib/utils'

type NoticeBannerProps = {
  tone?: 'info' | 'success' | 'danger'
  children: ReactNode
  className?: string
}

export function NoticeBanner({
  tone = 'info',
  children,
  className,
}: NoticeBannerProps) {
  const isDanger = tone === 'danger'
  const isSuccess = tone === 'success'

  return (
    <div
      role={isDanger ? 'alert' : 'status'}
      aria-live={isDanger ? 'assertive' : 'polite'}
      className={cn(
        'flex items-start gap-3 rounded-[calc(var(--radius-card)-0.16rem)] border px-4 py-3 text-sm leading-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.35)] backdrop-blur-[14px]',
        isDanger
          ? 'border-[color-mix(in_srgb,var(--danger)_18%,var(--line))] bg-[color-mix(in_srgb,var(--danger-surface)_94%,white)] text-[var(--danger)]'
          : isSuccess
            ? 'border-[color-mix(in_srgb,var(--success)_18%,var(--line))] bg-[color-mix(in_srgb,var(--success-surface)_94%,white)] text-[var(--success)]'
            : 'border-[color-mix(in_srgb,var(--primary)_18%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_8%,white)] text-[var(--foreground)]',
        className,
      )}
    >
      {isDanger ? (
        <WarningCircle className="mt-0.5 size-4 shrink-0" />
      ) : (
        <CheckCircle className="mt-0.5 size-4 shrink-0" />
      )}
      <div className="min-w-0">{children}</div>
    </div>
  )
}
