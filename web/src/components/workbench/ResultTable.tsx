import { useMemo } from 'react'

import { cn } from '@/lib/utils'

type Props = {
  rows: Record<string, unknown>[]
  className?: string
}

/** Tabular grid for `/api/v1/execution/run` row payloads — avoids raw JSON dumps. */
export function ResultTable({ rows, className }: Props) {
  const columns = useMemo(() => {
    const keys = new Set<string>()
    for (const r of rows) {
      for (const k of Object.keys(r)) keys.add(k)
    }
    return [...keys]
  }, [rows])

  if (rows.length === 0) {
    return (
      <p className="text-[11px] text-[var(--muted-foreground)]">未返回任何记录。</p>
    )
  }

  return (
    <div
      className={cn(
        'max-h-80 overflow-auto rounded-[calc(var(--radius-card)-0.15rem)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,transparent)]',
        className,
      )}
    >
      <table className="w-full min-w-[12rem] border-collapse text-left text-[11px]">
        <thead className="sticky top-0 z-10 bg-[color-mix(in_srgb,var(--surface-muted)_92%,white)] backdrop-blur-md">
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className="border-b border-[var(--line)] px-3 py-2 font-medium uppercase tracking-[0.12em] text-[var(--muted-foreground)]"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-[var(--line)] last:border-b-0 odd:bg-[color-mix(in_srgb,var(--surface-muted)_62%,white)]"
            >
              {columns.map((col) => (
                <td
                  key={col}
                  className="max-w-[14rem] px-3 py-2.5 align-top font-mono text-[10px] leading-5 text-[var(--foreground)] tabular-nums"
                  title={formatCell(row[col])}
                >
                  <span className="line-clamp-4 break-words">{formatCell(row[col])}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
