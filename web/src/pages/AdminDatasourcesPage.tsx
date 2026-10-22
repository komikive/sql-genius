import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowsClockwise,
  CheckCircle,
  Database,
  Lightning,
  Plus,
  StackSimple,
  WarningCircle,
} from '@phosphor-icons/react'

import type { AdminDatasourceSummary } from '@/lib/api'
import {
  getAdminDatasourceProfile,
  listAdminDatasources,
} from '@/lib/api'
import FadeContent from '@/components/FadeContent'
import { ProductEmptyState } from '@/components/layout/product-empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PageIntro } from '@/components/layout/page-intro'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

type DatasourceCardInfo = AdminDatasourceSummary & {
  analysis_status?: string
  table_count?: number
  skill_pack_count?: number
}

export function AdminDatasourcesPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<DatasourceCardInfo[]>([])
  const [loading, setLoading] = useState(true)

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const datasources = await listAdminDatasources()
      setItems(datasources.map((d) => ({ ...d })))

      const enriched = await Promise.allSettled(
        datasources.map(async (ds) => {
          try {
            const profile = await getAdminDatasourceProfile(ds.id)
            return {
              ...ds,
              analysis_status: profile.analysis_status,
              table_count: profile.profile_json
                ? ((profile.profile_json as Record<string, unknown>)?.schema_snapshot as Record<string, unknown>)?.table_count as number | undefined
                : undefined,
              skill_pack_count: profile.skill_packs?.length ?? 0,
            } satisfies DatasourceCardInfo
          } catch {
            return { ...ds } satisfies DatasourceCardInfo
          }
        }),
      )
      setItems(
        enriched.map((r) =>
          r.status === 'fulfilled' ? r.value : ({} as DatasourceCardInfo),
        ).filter((d) => d.id),
      )
    } catch {
      /* list failed, keep empty */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadList()
  }, [loadList])

  function statusIcon(status?: string) {
    switch (status) {
      case 'ready':
        return <CheckCircle className="size-4 text-emerald-500" weight="fill" />
      case 'running':
        return <Spinner className="size-4 text-blue-500" />
      case 'failed':
        return <WarningCircle className="size-4 text-red-400" weight="fill" />
      default:
        return <div className="size-4 rounded-full border-2 border-dashed border-[var(--line-strong)]" />
    }
  }

  function statusLabel(status?: string) {
    switch (status) {
      case 'ready': return '就绪'
      case 'running': return '分析中'
      case 'failed': return '失败'
      default: return '待分析'
    }
  }

  return (
    <>
      <PageIntro
        eyebrow="数据管理"
        title="数据源"
        description="连接外部数据库，采集结构，生成智能技能包。"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void loadList()}>
              <ArrowsClockwise className="size-3.5" />
              刷新
            </Button>
            <Button size="sm" onClick={() => navigate('/admin/datasources/new')}>
              <Plus className="size-3.5" />
              新建数据源
            </Button>
          </>
        }
      />

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner className="size-5 text-[var(--foreground-soft)]" />
        </div>
      ) : items.length === 0 ? (
        <FadeContent duration={400}>
          <ProductEmptyState
            icon={Database}
            title="还没有数据源"
            description="连接第一个数据库后，系统会自动采集结构并生成可用的查询资产。"
            action={(
              <Button size="sm" onClick={() => navigate('/admin/datasources/new')}>
                <Plus className="size-3.5" />
                新建数据源
              </Button>
            )}
          />
        </FadeContent>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((ds, index) => (
            <FadeContent key={ds.id} delay={40 + index * 50} duration={380}>
              <button
                type="button"
                onClick={() => navigate(`/admin/datasources/${encodeURIComponent(ds.id)}`)}
                className={cn(
                  'group flex min-h-[144px] w-full flex-col rounded-[1.55rem] border border-[color-mix(in_srgb,var(--line)_84%,white)] bg-[rgba(255,255,255,0.68)] p-4 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.62)] backdrop-blur-xl',
                  'transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]',
                  'hover:-translate-y-0.5 hover:border-[var(--line-strong)] hover:bg-white/78 hover:shadow-[0_14px_34px_rgba(17,24,39,0.07)]',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="truncate text-sm font-semibold text-[var(--foreground)]">
                        {ds.display_name || ds.id}
                      </h3>
                      {ds.is_default ? (
                        <Badge className="h-5 shrink-0 px-1.5 text-[9px]">默认</Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 truncate font-mono text-[11px] text-[var(--foreground-soft)]">
                      {ds.id}
                    </p>
                  </div>
                  {statusIcon(ds.analysis_status)}
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] text-[var(--foreground-soft)]">
                  <Badge variant="outline" className="h-5 px-1.5 text-[9px] uppercase">
                    {ds.dialect}
                  </Badge>
                  <span className="flex items-center gap-1">
                    {statusIcon(ds.analysis_status)}
                    {statusLabel(ds.analysis_status)}
                  </span>
                  {ds.table_count != null ? (
                    <span className="flex items-center gap-1">
                      <Database className="size-3" />
                      {ds.table_count} 表
                    </span>
                  ) : null}
                  {ds.skill_pack_count != null && ds.skill_pack_count > 0 ? (
                    <span className="flex items-center gap-1">
                      <StackSimple className="size-3" />
                      {ds.skill_pack_count} 技能包
                    </span>
                  ) : null}
                </div>

                {ds.last_introspected_at ? (
                  <p className="mt-3 text-[10px] text-[var(--muted-foreground)]">
                    上次采集: {new Date(ds.last_introspected_at).toLocaleString()}
                  </p>
                ) : null}

                <div className="mt-auto flex items-center gap-1 pt-3 text-[11px] font-medium text-[var(--primary)] opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                  <Lightning className="size-3" />
                  查看详情
                </div>
              </button>
            </FadeContent>
          ))}
        </div>
      )}
    </>
  )
}
