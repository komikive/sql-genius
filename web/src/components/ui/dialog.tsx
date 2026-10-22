"use client"

import * as React from 'react'

import { cn } from '@/lib/utils'

function Dialog({ children }: React.PropsWithChildren) {
  return <>{children}</>
}

function DialogTrigger(props: React.ComponentProps<'button'>) {
  return <button type="button" {...props} />
}

function DialogPortal({ children }: React.PropsWithChildren) {
  return <>{children}</>
}

function DialogClose(props: React.ComponentProps<'button'>) {
  return <button type="button" {...props} />
}

function DialogOverlay({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('fixed inset-0 z-40 bg-[rgba(17,24,39,0.24)] backdrop-blur-sm', className)}
      {...props}
    />
  )
}

function DialogContent({
  className,
  children,
  showCloseButton,
  ...props
}: React.ComponentProps<'div'> & {
  showCloseButton?: boolean
}) {
  return (
    <DialogPortal>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className={cn(
            'glass-shell relative w-full max-w-lg rounded-[var(--radius-page)] p-6',
            className,
          )}
          {...props}
        >
          {children}
          {showCloseButton ? (
            <button
              type="button"
              className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_84%,white)] text-[var(--foreground-soft)]"
              aria-label="Close"
            >
              ×
            </button>
          ) : null}
        </div>
      </div>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex flex-col gap-2', className)} {...props} />
}

function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('mt-4 flex items-center justify-end gap-2', className)} {...props} />
}

function DialogTitle({ className, ...props }: React.ComponentProps<'h2'>) {
  return (
    <h2
      className={cn('text-lg font-semibold tracking-[-0.03em] text-[var(--foreground)]', className)}
      {...props}
    />
  )
}

function DialogDescription({ className, ...props }: React.ComponentProps<'p'>) {
  return <p className={cn('text-sm leading-6 text-[var(--foreground-soft)]', className)} {...props} />
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
