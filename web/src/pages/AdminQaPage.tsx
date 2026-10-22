import { useEffect, useMemo, useState } from 'react'
import { ArrowsClockwise, Database, MagnifyingGlass, Sparkle } from '@phosphor-icons/react'
import { useSearchParams } from 'react-router-dom'

import type { AdminDatasourceQaExample, AdminDatasourceSummary } from '@/lib/api'
import { listAdminDatasources, listAdminQaExamples } from '@/lib/api'
import { NoticeBanner } from '@/components/layout/notice-banner'
import { PageIntro } from '@/components/layout/page-intro'
import { ProductEmptyState } from '@/components/layout/product-empty-state'
import { ProductSelect } from '@/components/layout/product-select'
import { SqlBlock } from '@/components/workbench/SqlBlock'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { embeddingStatusLabel, learningSourceLabel } from '@/lib/semanticLabels'

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '暂无'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

export function AdminQaPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const datasourceId = searchParams.get('datasource_id') ?? 'all'

  const [datasources, setDatasources] = useState<AdminDatasourceSummary[]>([])
  const [examples, setExamples] = useState<AdminDatasourceQaExample[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState(searchParams.get('q') ?? '')

  useEffect(() => {
    let cancelled = false
    void listAdminDatasources()
      .then((items) => {
        if (!cancelled) setDatasources(items)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载数据源失败')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const loadExamples = async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const items = await listAdminQaExamples(datasourceId === 'all' ? undefined : { datasourceId })
      setExamples(items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载问答案例失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    void loadExamples()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasourceId])

  const datasourceLabelMap = useMemo(
    () => new Map(datasources.map((item) => [item.id, item.display_name || item.id])),
    [datasources],
  )
  const datasourceOptions = useMemo(
    () => [
      { value: 'all', label: '全部数据源', description: '查看所有自动沉淀案例' },
      ...datasources.map((item) => ({
        value: item.id,
        label: item.display_name || item.id,
        description: item.id,
      })),
    ],
    [datasources],
  )

  const filteredExamples = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return examples
    return examples.filter((item) =>
      [item.question, item.note, item.sql, ...(item.scenario_tags || [])].join(' ').toLowerCase().includes(needle),
    )
  }, [examples, query])

  return (
    <div className="space-y-6">
      <PageIntro
        eyebrow="QA 案例层"
        title="问答案例"
        description="这里展示系统在真实运行中自动沉淀的高价值问答对。它们独立于技能文档存在，主要服务于相似问题的语义检索，不要求人工维护。"
        actions={(
          <Button variant="outline" size="sm" onClick={() => void loadExamples(true)} disabled={refreshing}>
            {refreshing ? <Spinner className="size-3.5" /> : <ArrowsClockwise className="size-3.5" />}
            刷新案例
          </Button>
        )}
        stats={[
          { title: `${examples.length} 条案例`, detail: '当前筛选范围内的自动沉淀问答案例。', icon: Sparkle },
          { title: datasourceId === 'all' ? '全部数据源' : datasourceLabelMap.get(datasourceId) ?? datasourceId, detail: '可按数据源收窄案例范围。', icon: Database },
        ]}
      />

      {error ? <NoticeBanner tone="danger">{error}</NoticeBanner> : null}

      <Card className="z-20 overflow-visible rounded-[1.65rem] bg-white/62 shadow-[0_14px_40px_rgba(17,24,39,0.05)]">
        <CardContent className="grid gap-3 p-4 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="space-y-2 text-xs font-medium text-[var(--foreground)]">
            <span>数据源</span>
            <ProductSelect
              value={datasourceId}
              options={datasourceOptions}
              onChange={(value) => {
                const next = new URLSearchParams(searchParams)
                if (value === 'all') next.delete('datasource_id')
                else next.set('datasource_id', value)
                setSearchParams(next, { replace: true })
              }}
            />
          </div>

          <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
            <span>关键词</span>
            <div className="relative">
              <MagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索问题、SQL、说明或场景标签"
                className="h-10 pl-9"
              />
            </div>
          </label>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <Spinner className="size-5 text-[var(--foreground-soft)]" />
        </div>
      ) : filteredExamples.length === 0 ? (
        <ProductEmptyState
          icon={Sparkle}
          title="暂无问答案例"
          description="随着真实问答累计并达到稳定条件，系统会自动沉淀可复用的高价值案例。"
        />
      ) : (
        <div className="space-y-4">
          {filteredExamples.map((item) => (
            <Card
              key={item.id}
              className="overflow-hidden border-[color-mix(in_srgb,var(--line-strong)_22%,var(--line))] bg-white/72 shadow-[0_10px_36px_rgba(17,24,39,0.04)]"
            >
              <CardContent className="grid gap-5 p-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:p-6">
                <div className="flex min-w-0 flex-col gap-4">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-[color-mix(in_srgb,var(--surface-strong)_72%,transparent)] px-2.5 py-1 font-medium text-[var(--foreground)]">
                        <Database className="size-3" weight="duotone" />
                        {datasourceLabelMap.get(item.datasource_id) ?? item.datasource_id}
                      </span>
                      <Badge variant="outline" className="text-[10px]">
                        {learningSourceLabel(item.source)}
                      </Badge>
                      <Badge variant="outline" className="text-[10px]">
                        {embeddingStatusLabel(item.embedding_status)}
                      </Badge>
                    </div>
                    <h3 className="text-[15px] font-semibold leading-snug text-[var(--foreground)]">
                      {item.question}
                    </h3>
                  </div>

                  {item.note ? (
                    <p className="rounded-xl border border-dashed border-[color-mix(in_srgb,var(--line-strong)_25%,var(--line))] bg-[color-mix(in_srgb,var(--surface-strong)_55%,transparent)] px-3.5 py-2.5 text-[12.5px] leading-6 text-[var(--foreground-soft)]">
                      {item.note}
                    </p>
                  ) : null}

                  <div className="flex flex-wrap items-center gap-1.5">
                    {item.scenario_tags.length === 0 ? (
                      <span className="text-[11px] text-[var(--muted-foreground)]">未标注场景</span>
                    ) : (
                      item.scenario_tags.map((tag) => (
                        <Badge
                          key={`${item.id}-${tag}`}
                          variant="outline"
                          className="rounded-full border-[color-mix(in_srgb,var(--line-strong)_30%,var(--line))] bg-white/60 px-2 py-0.5 text-[10.5px] font-medium text-[var(--foreground-soft)]"
                        >
                          # {tag}
                        </Badge>
                      ))
                    )}
                  </div>

                  <div className="mt-auto text-[10.5px] uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                    更新于 {formatDateTime(item.updated_at)}
                  </div>
                </div>

                <SqlBlock sql={item.sql || '-- 暂无 SQL --'} className="self-start" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
