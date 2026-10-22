import { useEffect, useMemo, useState } from 'react'
import {
  ArrowsClockwise,
  Brain,
  Database,
  MagnifyingGlass,
  Sparkle,
} from '@phosphor-icons/react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import type { AdminDatasourceSummary, AdminSkillPackSummary } from '@/lib/api'
import { listAdminDatasources, listAdminSkillPacks } from '@/lib/api'
import { NoticeBanner } from '@/components/layout/notice-banner'
import { PageIntro } from '@/components/layout/page-intro'
import { ProductEmptyState } from '@/components/layout/product-empty-state'
import { ProductSelect } from '@/components/layout/product-select'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

function originLabel(value: string): string {
  if (value === 'onboarding') return '初始化'
  if (value === 'runtime-learning') return '运行时'
  if (value === 'system') return '系统'
  return value
}

export function AdminSkillsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const datasourceId = searchParams.get('datasource_id') ?? 'all'

  const [datasources, setDatasources] = useState<AdminDatasourceSummary[]>([])
  const [packs, setPacks] = useState<AdminSkillPackSummary[]>([])
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

  const loadPacks = async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const items = await listAdminSkillPacks(datasourceId === 'all' ? undefined : datasourceId)
      setPacks(items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载技能失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    void loadPacks()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasourceId])

  const datasourceLabelMap = useMemo(
    () =>
      new Map(datasources.map((item) => [item.id, item.display_name || item.id])),
    [datasources],
  )

  const activePacks = useMemo(
    () => packs.filter((pack) => !['superseded', 'rejected'].includes(pack.status)),
    [packs],
  )

  const datasourceOptions = useMemo(
    () => [
      { value: 'all', label: '全部数据源', description: '查看当前所有可用技能' },
      ...datasources.map((item) => ({
        value: item.id,
        label: item.display_name || item.id,
        description: item.id,
      })),
    ],
    [datasources],
  )

  const filteredPacks = useMemo(() => {
    return activePacks.filter((pack) => {
      if (!query.trim()) return true
      const haystack = [
        pack.name,
        pack.summary,
        pack.slug,
        ...(pack.keywords || []),
        ...(pack.table_focus || []),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(query.trim().toLowerCase())
    })
  }, [activePacks, query])

  const datasourceScopedCount = activePacks.filter((item) => item.datasource_id).length
  const runtimeCount = activePacks.filter((item) => item.origin === 'runtime-learning').length
  const tableFocusCount = new Set(activePacks.flatMap((item) => item.table_focus || [])).size

  return (
    <div className="space-y-6">
      <PageIntro
        eyebrow="技能资产"
        title="技能目录"
        description="所有展示项均是当前可被 Agent 使用的技能资产。历史替代项和废弃项会自动从目录中隐藏。"
        actions={(
          <Button variant="outline" size="sm" onClick={() => void loadPacks(true)} disabled={refreshing}>
            {refreshing ? <Spinner className="size-3.5" /> : <ArrowsClockwise className="size-3.5" />}
            刷新目录
          </Button>
        )}
        stats={[
          { title: `${activePacks.length} 个技能`, detail: '当前目录中的可用技能资产。', icon: Brain },
          { title: `${datasourceScopedCount} 个数据源技能`, detail: '绑定到具体数据源，可被工作台自动召回。', icon: Database },
          { title: `${tableFocusCount} 个表焦点`, detail: '技能覆盖的核心表范围。', icon: Sparkle },
          { title: `${runtimeCount} 个运行时来源`, detail: '由真实对话沉淀出的技能资产。', icon: Brain },
        ]}
      />

      {error ? <NoticeBanner tone="danger">{error}</NoticeBanner> : null}

      <Card className="z-20 overflow-visible rounded-[1.65rem] bg-white/62 shadow-[0_14px_40px_rgba(17,24,39,0.05)]">
        <CardHeader className="pb-3">
          <CardTitle>筛选视图</CardTitle>
          <CardDescription>
            先按数据源收窄范围，再按关键词搜索技能名称、摘要和表焦点。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
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
                placeholder="搜索技能名、摘要、关键词或表焦点"
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
      ) : filteredPacks.length === 0 ? (
        <ProductEmptyState
          icon={Brain}
          title="当前筛选下没有技能"
          description="可以切换数据源、调整关键词，或重新分析数据源来生成技能资产。"
        />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2 2xl:grid-cols-3">
          {filteredPacks.map((pack) => {
            const effectiveDatasourceId = pack.datasource_id ?? undefined
            return (
              <Card
                key={pack.id}
                className="border-[color-mix(in_srgb,var(--line-strong)_28%,var(--line))] bg-white/66 transition-[transform,box-shadow,border-color,background-color] duration-200 hover:-translate-y-0.5 hover:bg-white/78 hover:shadow-[0_16px_38px_rgba(15,23,42,0.07)]"
              >
                <CardHeader className="space-y-2 pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <CardTitle className="text-[16px]">{pack.name}</CardTitle>
                      <div className="text-[11px] text-[var(--muted-foreground)]">{pack.slug}</div>
                    </div>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Badge variant="outline">{originLabel(pack.origin)}</Badge>
                    </div>
                  </div>
                  <CardDescription className="line-clamp-2 min-h-[48px] text-[13px] leading-6">
                    {pack.summary || '暂无摘要'}
                  </CardDescription>
                </CardHeader>

                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded-xl border border-[var(--line)] bg-white/42 px-3 py-2">
                      <div className="text-[10px] text-[var(--muted-foreground)]">置信度</div>
                      <div className="mt-1 font-semibold text-[var(--foreground)]">
                        {Math.round(pack.confidence * 100)}%
                      </div>
                    </div>
                    <div className="rounded-xl border border-[var(--line)] bg-white/42 px-3 py-2">
                      <div className="text-[10px] text-[var(--muted-foreground)]">表焦点</div>
                      <div className="mt-1 font-semibold text-[var(--foreground)]">{pack.table_focus.length}</div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="text-[11px] font-medium text-[var(--muted-foreground)]">关键词</div>
                    <div className="flex flex-wrap gap-1.5">
                      {(pack.keywords || []).slice(0, 6).map((keyword) => (
                        <Badge key={keyword} variant="outline" className="text-[10px]">
                          {keyword}
                        </Badge>
                      ))}
                      {pack.keywords.length === 0 ? (
                        <span className="text-xs text-[var(--muted-foreground)]">暂无关键词</span>
                      ) : null}
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-3 border-t border-[var(--line)] pt-3">
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                        Datasource
                      </div>
                      <div className="truncate text-sm font-medium text-[var(--foreground)]">
                        {effectiveDatasourceId
                          ? datasourceLabelMap.get(effectiveDatasourceId) ?? effectiveDatasourceId
                          : '未绑定数据源'}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {effectiveDatasourceId ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => navigate(`/admin/datasources/${encodeURIComponent(effectiveDatasourceId)}`)}
                        >
                          数据源
                        </Button>
                      ) : null}
                      <Button
                        size="sm"
                        onClick={() =>
                          navigate(
                            `/admin/skills/${encodeURIComponent(pack.id)}${
                              effectiveDatasourceId
                                ? `?datasource_id=${encodeURIComponent(effectiveDatasourceId)}`
                                : ''
                            }`,
                          )
                        }
                      >
                        查看详情
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
