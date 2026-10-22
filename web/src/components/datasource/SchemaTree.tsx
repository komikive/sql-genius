import { useMemo, useState } from 'react'
import {
  CaretDown,
  CaretRight,
  Database,
  MagnifyingGlass,
} from '@phosphor-icons/react'

import type { DatasourceSchemaPayload } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type SchemaTreeProps = {
  schema: DatasourceSchemaPayload
  className?: string
  maxHeight?: string
}

export function SchemaTree({ schema, className, maxHeight = '480px' }: SchemaTreeProps) {
  const [query, setQuery] = useState('')
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return schema.tables
    return schema.tables.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.comment ?? '').toLowerCase().includes(q) ||
        t.columns.some(
          (c) =>
            c.name.toLowerCase().includes(q) ||
            (c.comment ?? '').toLowerCase().includes(q),
        ),
    )
  }, [schema.tables, query])

  function toggleTable(name: string) {
    setExpandedTables((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  function expandAll() {
    setExpandedTables(new Set(filtered.map((t) => t.name)))
  }

  function collapseAll() {
    setExpandedTables(new Set())
  }

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <MagnifyingGlass className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索表名或字段名…"
            className="h-8 pl-8 text-xs"
          />
        </div>
        <button
          type="button"
          onClick={expandAll}
          className="text-[11px] font-medium text-[var(--primary)] hover:underline"
        >
          全部展开
        </button>
        <button
          type="button"
          onClick={collapseAll}
          className="text-[11px] font-medium text-[var(--foreground-soft)] hover:underline"
        >
          收起
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-[11px] text-[var(--foreground-soft)]">
        <span>{schema.table_count} 个表</span>
        <span>{schema.column_count} 个字段</span>
        <Badge variant="outline" className="h-4 px-1 text-[8px] uppercase">
          {schema.dialect}
        </Badge>
        {schema.truncated ? (
          <Badge variant="outline" className="h-4 px-1 text-[8px]">已截断</Badge>
        ) : null}
      </div>

      <div
        className="overflow-y-auto rounded-xl border border-[var(--line)] bg-[var(--surface)]"
        style={{ maxHeight }}
      >
        {filtered.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-[var(--muted-foreground)]">
            {query ? '没有匹配的表或字段' : '暂无表结构数据'}
          </div>
        ) : (
          <div className="divide-y divide-[var(--line)]">
            {filtered.map((table) => {
              const isExpanded = expandedTables.has(table.name)
              return (
                <div key={table.name}>
                  <button
                    type="button"
                    onClick={() => toggleTable(table.name)}
                    className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-[color-mix(in_srgb,var(--surface-strong)_50%,white)]"
                  >
                    {isExpanded ? (
                      <CaretDown className="size-3 shrink-0 text-[var(--muted-foreground)]" />
                    ) : (
                      <CaretRight className="size-3 shrink-0 text-[var(--muted-foreground)]" />
                    )}
                    <Database className="size-3.5 shrink-0 text-[var(--primary)]" />
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono text-xs font-medium text-[var(--foreground)]">
                        {table.name}
                      </span>
                      {table.comment ? (
                        <span className="mt-0.5 block truncate text-[11px] text-[var(--foreground-soft)]">
                          {table.comment}
                        </span>
                      ) : null}
                    </span>
                    <span className="ml-auto text-[10px] text-[var(--muted-foreground)]">
                      {table.columns.length} 列
                    </span>
                  </button>

                  {isExpanded ? (
                    <div className="border-t border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_60%,white)]">
                      <table className="w-full">
                        <thead>
                          <tr className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
                            <th className="py-1.5 pl-10 pr-2 text-left font-medium">字段名</th>
                            <th className="px-2 py-1.5 text-left font-medium">类型</th>
                            <th className="px-2 py-1.5 text-left font-medium">注释</th>
                            <th className="px-2 py-1.5 text-left font-medium">可空</th>
                          </tr>
                        </thead>
                        <tbody>
                          {table.columns.map((col) => (
                            <tr
                              key={col.name}
                              className="border-t border-[color-mix(in_srgb,var(--line)_50%,transparent)] text-[11px]"
                            >
                              <td className="py-1 pl-10 pr-2 font-mono text-[var(--foreground)]">
                                {col.name}
                              </td>
                              <td className="px-2 py-1">
                                <Badge variant="outline" className="h-4 px-1 text-[8px]">
                                  {col.type}
                                </Badge>
                              </td>
                              <td className="max-w-[320px] px-2 py-1 text-[var(--foreground-soft)]">
                                {col.comment ? (
                                  <span title={col.comment} className="line-clamp-2">
                                    {col.comment}
                                  </span>
                                ) : (
                                  <span className="text-[var(--muted-foreground)]">—</span>
                                )}
                              </td>
                              <td className="px-2 py-1 text-[var(--muted-foreground)]">
                                {col.nullable ? 'YES' : 'NO'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
