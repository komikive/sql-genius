import type { ReactNode } from 'react'
import type { Icon } from '@phosphor-icons/react'

import FadeContent from '@/components/FadeContent'
import { cn } from '@/lib/utils'

type IntroStat = {
  title: string
  detail: string
  icon?: Icon
}

type PageIntroProps = {
  eyebrow?: string
  title: string
  description?: string
  stats?: IntroStat[]
  statsTitle?: string
  actions?: ReactNode
  className?: string
}

export function PageIntro({
  eyebrow,
  title,
  description,
  stats = [],
  actions,
  className,
}: PageIntroProps) {
  return (
    <FadeContent duration={400}>
      <section className={cn('space-y-4', className)}>
        <div className="flex flex-col gap-4 rounded-[1.8rem] border border-[color-mix(in_srgb,var(--line)_78%,white)] bg-[linear-gradient(180deg,rgba(255,255,255,0.58),rgba(255,255,255,0.26))] px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.58)] backdrop-blur-xl lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1.5">
            {eyebrow ? <div className="section-label">{eyebrow}</div> : null}
            <h1 className="text-[22px] font-semibold tracking-[-0.04em] text-[var(--foreground)]">
              {title}
            </h1>
            {description ? (
              <p className="max-w-[62ch] text-[13px] leading-6 text-[var(--foreground-soft)]">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>

        {stats.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map((stat, index) => {
              const StatIcon = stat.icon
              return (
                <FadeContent key={stat.title} delay={80 + index * 60} duration={360}>
                  <div className="rounded-[1.15rem] border border-[color-mix(in_srgb,var(--line)_84%,white)] bg-[rgba(255,255,255,0.66)] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.62)] backdrop-blur-xl transition-[transform,border-color,box-shadow] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-px hover:border-[var(--line-strong)] hover:shadow-[0_12px_28px_rgba(17,24,39,0.05)]">
                    <div className="flex items-center gap-2">
                      {StatIcon ? (
                        <span className="flex size-7 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--primary)_9%,white)] text-[var(--primary)]">
                          <StatIcon className="size-3.5" />
                        </span>
                      ) : null}
                      <span className="text-[13px] font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                        {stat.title}
                      </span>
                    </div>
                    <p className="mt-2 text-[11px] leading-5 text-[var(--foreground-soft)]">
                      {stat.detail}
                    </p>
                  </div>
                </FadeContent>
              )
            })}
          </div>
        ) : null}
      </section>
    </FadeContent>
  )
}
