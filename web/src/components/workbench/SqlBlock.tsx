import { useCallback, useMemo, useState } from 'react'
import { Check, Copy } from '@phosphor-icons/react'

import { Button } from '@/components/ui/button'
import { formatSqlForDisplay, renderHighlightedSql } from '@/lib/sqlHighlight'
import { cn } from '@/lib/utils'

type Props = {
  sql: string
  className?: string
}

/** Calm SQL block with lightweight syntax highlighting and copy. */
export function SqlBlock({ sql, className }: Props) {
  const [copied, setCopied] = useState(false)
  const formattedSql = useMemo(() => formatSqlForDisplay(sql), [sql])

  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(formattedSql)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }, [formattedSql])

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-[calc(var(--radius-card)-0.15rem)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,transparent)] shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2">
        <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
          SQL 预览
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 rounded-full px-2 text-[11px]"
          onClick={() => void onCopy()}
        >
          {copied ? (
            <Check className="size-3.5" weight="bold" />
          ) : (
            <Copy className="size-3.5" />
          )}
          {copied ? '已复制' : '复制'}
        </Button>
      </div>
      <pre className="max-h-72 overflow-auto px-3 py-3 font-mono text-[11px] leading-6 whitespace-pre-wrap text-[var(--foreground)]">
        {renderHighlightedSql(formattedSql)}
      </pre>
    </div>
  )
}
