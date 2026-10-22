import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { CaretDown, Check } from '@phosphor-icons/react'

import { cn } from '@/lib/utils'

export type ProductSelectOption = {
  value: string
  label: string
  description?: string
}

type ProductSelectProps = {
  value: string
  options: ProductSelectOption[]
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
  /** Native tooltip, useful when disabled (e.g. thread-bound datasource). */
  title?: string
}

export function ProductSelect({
  value,
  options,
  onChange,
  placeholder = '请选择',
  className,
  disabled,
  title,
}: ProductSelectProps) {
  const [open, setOpen] = useState(false)
  const [menuStyle, setMenuStyle] = useState<{
    left: number
    top: number
    width: number
    placement: 'top' | 'bottom'
  } | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const selected = options.find((item) => item.value === value)
  const isOpen = open && !disabled

  useEffect(() => {
    if (disabled) setOpen(false)
  }, [disabled])

  const updateMenuPosition = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const spaceBelow = window.innerHeight - rect.bottom
    const placement = spaceBelow < 260 && rect.top > spaceBelow ? 'top' : 'bottom'
    setMenuStyle({
      left: rect.left,
      top: placement === 'top' ? rect.top - 8 : rect.bottom + 8,
      width: rect.width,
      placement,
    })
  }

  useLayoutEffect(() => {
    if (!isOpen) return
    const frame = window.requestAnimationFrame(updateMenuPosition)
    return () => window.cancelAnimationFrame(frame)
  }, [isOpen, options.length, value])

  useEffect(() => {
    if (!isOpen) return
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node
      if (
        ref.current &&
        !ref.current.contains(target) &&
        menuRef.current &&
        !menuRef.current.contains(target)
      ) {
        setOpen(false)
      }
    }
    function handleViewportChange() {
      updateMenuPosition()
    }
    document.addEventListener('mousedown', handlePointerDown)
    window.addEventListener('resize', handleViewportChange)
    window.addEventListener('scroll', handleViewportChange, true)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      window.removeEventListener('resize', handleViewportChange)
      window.removeEventListener('scroll', handleViewportChange, true)
    }
  }, [isOpen])

  return (
    <div ref={ref} className={cn('relative', className)}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        title={title}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        onClick={() => setOpen((current) => !current)}
        className="flex h-10 w-full items-center justify-between gap-3 rounded-2xl border border-[color-mix(in_srgb,var(--line)_86%,white)] bg-white/76 px-3 text-left text-sm text-[var(--foreground)] shadow-[0_8px_22px_rgba(17,24,39,0.04),inset_0_1px_0_rgba(255,255,255,0.62)] outline-none backdrop-blur-xl transition-[border-color,box-shadow,background-color] duration-200 hover:border-[var(--line-strong)] hover:bg-white/90 focus-visible:border-[color-mix(in_srgb,var(--primary)_36%,var(--line))] focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--primary)_14%,transparent)] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span className="min-w-0">
          <span className="block truncate text-[13px] font-medium">
            {selected?.label ?? placeholder}
          </span>
          {selected?.description ? (
            <span className="mt-0.5 block truncate text-[10px] text-[var(--muted-foreground)]">
              {selected.description}
            </span>
          ) : null}
        </span>
        <CaretDown
          className={cn(
            'size-3.5 shrink-0 text-[var(--muted-foreground)] transition-transform duration-200',
            isOpen && 'rotate-180',
          )}
        />
      </button>

      {isOpen && menuStyle ? createPortal(
        <div
          ref={menuRef}
          role="listbox"
          style={{
            left: menuStyle.left,
            top: menuStyle.top,
            width: menuStyle.width,
            transform: menuStyle.placement === 'top' ? 'translateY(-100%)' : undefined,
          }}
          className="fixed z-[9999] overflow-hidden rounded-2xl border border-[var(--line)] bg-[rgba(255,255,255,0.96)] p-1 shadow-[0_24px_64px_rgba(17,24,39,0.16),inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-2xl"
        >
          <div className="max-h-72 overflow-y-auto">
            {options.map((option) => {
              const active = option.value === value
              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onChange(option.value)
                    setOpen(false)
                  }}
                  className={cn(
                    'flex w-full items-start justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors duration-150',
                    active
                      ? 'bg-[color-mix(in_srgb,var(--primary)_9%,white)] text-[var(--foreground)]'
                      : 'text-[var(--foreground-soft)] hover:bg-[color-mix(in_srgb,var(--surface)_74%,white)] hover:text-[var(--foreground)]',
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium">{option.label}</span>
                    {option.description ? (
                      <span className="mt-0.5 block truncate text-[10px] text-[var(--muted-foreground)]">
                        {option.description}
                      </span>
                    ) : null}
                  </span>
                  {active ? <Check className="mt-0.5 size-3.5 shrink-0 text-[var(--primary)]" /> : null}
                </button>
              )
            })}
          </div>
        </div>
      , document.body) : null}
    </div>
  )
}
