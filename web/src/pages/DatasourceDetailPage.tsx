import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowsClockwise,
  Brain,
  Database,
  Trash,
  WarningCircle,
} from '@phosphor-icons/react'

import type {
  AdminDatasourceDetail,
  AdminDatasourceProfile,
  AdminSkillPackSummary,
  DatasourceSchemaPayload,
} from '@/lib/api'
import {
  deleteAdminDatasource,
  getAdminDatasource,
  getAdminDatasourceProfile,
  getAdminDatasourceSchema,
  introspectAdminDatasource,
  listAdminSkillPacks,
  runAdminDatasourceOnboarding,
  updateAdminDatasource,
} from '@/lib/api'
import FadeContent from '@/components/FadeContent'
import { SchemaTree } from '@/components/datasource/SchemaTree'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

type Tab = 'overview' | 'schema'

export function DatasourceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const datasourceId = id ?? ''

  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<AdminDatasourceDetail | null>(null)
  const [profile, setProfile] = useState<AdminDatasourceProfile | null>(null)
  const [schema, setSchema] = useState<DatasourceSchemaPayload | null>(null)
  const [skillPacks, setSkillPacks] = useState<AdminSkillPackSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    if (!datasourceId) return
    setLoading(true)
    setError(null)
    try {
      const [det, prof, packs] = await Promise.all([
        getAdminDatasource(datasourceId),
        getAdminDatasourceProfile(datasourceId).catch(() => null),
        listAdminSkillPacks(datasourceId),
      ])
      setDetail(det)
      setProfile(prof)
      setSkillPacks(packs)

      if (det.schema_available) {
        const s = await getAdminDatasourceSchema(datasourceId).catch(() => null)
        setSchema(s)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [datasourceId])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'overview', label: '概览' },
    { key: 'schema', label: '结构浏览', count: schema?.table_count },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="size-5 text-[var(--foreground-soft)]" />
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="py-20 text-center text-sm text-[var(--foreground-soft)]">
        数据源未找到
      </div>
    )
  }

  return (
    <div>
      <FadeContent duration={400}>
        <button
          type="button"
          onClick={() => navigate('/admin/datasources')}
          className="mb-4 flex items-center gap-1.5 text-xs font-medium text-[var(--foreground-soft)] transition-colors hover:text-[var(--foreground)]"
        >
          <ArrowLeft className="size-3.5" />
          返回数据源列表
        </button>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--primary)]">
              <Database className="size-5" weight="duotone" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold tracking-tight text-[var(--foreground)]">
                  {detail.display_name || detail.id}
                </h1>
                {detail.is_default ? <Badge className="h-5 px-1.5 text-[9px]">默认</Badge> : null}
                <Badge variant="outline" className="h-5 px-1.5 text-[9px] uppercase">
                  {detail.dialect}
                </Badge>
              </div>
              <p className="mt-0.5 font-mono text-[11px] text-[var(--foreground-soft)]">{detail.id}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void loadAll()}>
              <ArrowsClockwise className="size-3.5" />
              刷新
            </Button>
          </div>
        </div>
      </FadeContent>

      {error ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          <WarningCircle className="mt-0.5 size-4 shrink-0" weight="fill" />
          <span>{error}</span>
        </div>
      ) : null}

      {/* Tab bar */}
      <FadeContent duration={400} delay={80}>
        <div className="mt-6 flex gap-1 border-b border-[var(--line)]">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-xs font-medium transition-colors',
                tab === t.key
                  ? 'border-[var(--primary)] text-[var(--foreground)]'
                  : 'border-transparent text-[var(--foreground-soft)] hover:text-[var(--foreground)]',
              )}
            >
              {t.label}
              {t.count != null ? (
                <span className="rounded-full bg-[color-mix(in_srgb,var(--foreground)_8%,white)] px-1.5 py-0.5 text-[10px]">
                  {t.count}
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </FadeContent>

      <div className="mt-6">
        {tab === 'overview' ? (
          <OverviewTab
            detail={detail}
            profile={profile}
            schema={schema}
            skillPacks={skillPacks}
            memoryCount={profile?.active_memory_count ?? 0}
            onOpenSkills={() =>
              navigate(`/admin/skills?datasource_id=${encodeURIComponent(datasourceId)}`)
            }
            onOpenMemory={() =>
              navigate(`/admin/memory?datasource_id=${encodeURIComponent(datasourceId)}`)
            }
            onOpenQa={() =>
              navigate(`/admin/qa?datasource_id=${encodeURIComponent(datasourceId)}`)
            }
            onReanalyze={async () => {
              setError(null)
              try {
                const run = await runAdminDatasourceOnboarding(datasourceId)
                navigate(`/admin/history?datasource_id=${encodeURIComponent(datasourceId)}&run_id=${encodeURIComponent(run.id)}`)
              } catch (err) {
                setError(err instanceof Error ? err.message : '重新分析失败')
              }
            }}
            onIntrospect={async () => {
              setError(null)
              try {
                await introspectAdminDatasource(datasourceId)
                const s = await getAdminDatasourceSchema(datasourceId)
                setSchema(s)
              } catch (err) {
                setError(err instanceof Error ? err.message : '结构采集失败')
              }
            }}
            onUpdate={async (body) => {
              await updateAdminDatasource(datasourceId, body)
              const d = await getAdminDatasource(datasourceId)
              setDetail(d)
            }}
            onDelete={async () => {
              if (!window.confirm('确定删除此数据源？此操作不可撤销。')) return
              await deleteAdminDatasource(datasourceId)
              navigate('/admin/datasources')
            }}
          />
        ) : null}

        {tab === 'schema' ? (
          <FadeContent duration={400}>
            {schema ? (
              <SchemaTree schema={schema} />
            ) : (
              <div className="py-12 text-center text-xs text-[var(--foreground-soft)]">
                暂无结构数据，请先在「概览」中采集结构。
              </div>
            )}
          </FadeContent>
        ) : null}
      </div>
    </div>
  )
}

/* ---------- Overview Tab ---------- */

function OverviewTab({
  detail,
  profile,
  schema,
  skillPacks,
  memoryCount,
  onOpenSkills,
  onOpenMemory,
  onOpenQa,
  onReanalyze,
  onIntrospect,
  onUpdate,
  onDelete,
}: {
  detail: AdminDatasourceDetail
  profile: AdminDatasourceProfile | null
  schema: DatasourceSchemaPayload | null
  skillPacks: AdminSkillPackSummary[]
  memoryCount: number
  onOpenSkills: () => void
  onOpenMemory: () => void
  onOpenQa: () => void
  onReanalyze: () => Promise<void>
  onIntrospect: () => Promise<void>
  onUpdate: (body: { display_name?: string; is_default?: boolean }) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const [analyzing, setAnalyzing] = useState(false)
  const [introspecting, setIntrospecting] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(detail.display_name)

  const analysisStatus = profile?.analysis_status ?? 'pending'

  return (
    <FadeContent duration={400}>
      <div className="grid gap-5 xl:grid-cols-2">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:col-span-2">
          {[
            { label: '分析状态', value: analysisStatus === 'ready' ? '就绪' : analysisStatus === 'running' ? '分析中' : analysisStatus === 'failed' ? '失败' : '待分析' },
            { label: '表数量', value: schema?.table_count ?? '—' },
            { label: '技能包', value: skillPacks.length },
            { label: '记忆条目', value: memoryCount },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
            >
              <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                {stat.label}
              </p>
              <p className="mt-1 text-lg font-semibold text-[var(--foreground)]">{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Connection info */}
        <div className="rounded-[var(--radius-page)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-[var(--foreground)]">连接信息</h3>
            <button
              type="button"
              onClick={() => setEditing(!editing)}
              className="text-[11px] font-medium text-[var(--primary)] hover:underline"
            >
              {editing ? '取消' : '编辑'}
            </button>
          </div>
          <div className="mt-3 space-y-2 text-xs">
            {editing ? (
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-[11px] text-[var(--foreground-soft)]">显示名称</label>
                  <Input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
                <Button
                  size="sm"
                  className="h-7 text-[11px]"
                  onClick={async () => {
                    await onUpdate({ display_name: editName })
                    setEditing(false)
                  }}
                >
                  保存
                </Button>
              </div>
            ) : (
              <>
                <div className="flex justify-between">
                  <span className="text-[var(--foreground-soft)]">ID</span>
                  <span className="font-mono text-[var(--foreground)]">{detail.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--foreground-soft)]">类型</span>
                  <span className="text-[var(--foreground)]">{detail.dialect}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--foreground-soft)]">连接</span>
                  <span className="truncate pl-4 font-mono text-[var(--foreground)]">
                    {detail.connection_url_masked}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--foreground-soft)]">上次采集</span>
                  <span className="text-[var(--foreground)]">
                    {detail.last_introspected_at
                      ? new Date(detail.last_introspected_at).toLocaleString()
                      : '暂无'}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Profile summary */}
        <div className="rounded-[var(--radius-page)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
          <h3 className="text-xs font-semibold text-[var(--foreground)]">画像摘要</h3>
          {profile?.summary ? (
            <p className="mt-2 text-xs leading-5 text-[var(--foreground-soft)]">{profile.summary}</p>
          ) : (
            <p className="mt-2 text-xs text-[var(--muted-foreground)]">暂无画像。请先运行智能分析。</p>
          )}
          {profile?.last_analyzed_at ? (
            <p className="mt-3 text-[10px] text-[var(--muted-foreground)]">
              上次分析: {new Date(profile.last_analyzed_at).toLocaleString()}
            </p>
          ) : null}
        </div>

        <div className="rounded-[var(--radius-page)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)] xl:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-xs font-semibold text-[var(--foreground)]">资产治理入口</h3>
              <p className="mt-1 text-xs leading-5 text-[var(--foreground-soft)]">
                技能、记忆与问答案例已升级为一级栏目；这里保留为数据源控制面与带筛选跳转入口。
              </p>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {[
              {
                key: 'skills',
                title: '技能',
                detail: `当前 ${skillPacks.length} 个技能包，适合做覆盖面梳理和重生成。`,
                count: skillPacks.length,
                icon: Brain,
                onClick: onOpenSkills,
              },
              {
                key: 'memory',
                title: '记忆',
                detail: `当前 ${memoryCount} 条记忆，可跳转到全局记忆页并自动锁定本数据源。`,
                count: memoryCount,
                icon: Database,
                onClick: onOpenMemory,
              },
              {
                key: 'qa',
                title: '问答案例',
                detail: '查看系统在真实运行中自动沉淀的高价值问答案例。',
                count: 0,
                icon: WarningCircle,
                onClick: onOpenQa,
              },
            ].map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={item.onClick}
                  className="surface-card-interactive rounded-xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_78%,white)] px-4 py-4 text-left transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--primary)]">
                      <Icon className="size-4" />
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-[var(--foreground)]">
                        {item.title}
                      </div>
                      <div className="text-[10px] text-[var(--muted-foreground)]">
                        数量 {item.count}
                      </div>
                    </div>
                  </div>
                  <p className="mt-3 text-xs leading-5 text-[var(--foreground-soft)]">
                    {item.detail}
                  </p>
                </button>
              )
            })}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2 xl:col-span-2">
          <Button
            variant="outline"
            size="sm"
            disabled={introspecting}
            onClick={async () => {
              setIntrospecting(true)
              try { await onIntrospect() } finally { setIntrospecting(false) }
            }}
          >
            {introspecting ? <Spinner className="size-3.5" /> : <Database className="size-3.5" />}
            采集结构
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={analyzing}
            onClick={async () => {
              setAnalyzing(true)
              try { await onReanalyze() } finally { setAnalyzing(false) }
            }}
          >
            {analyzing ? <Spinner className="size-3.5" /> : <Brain className="size-3.5" />}
            重新分析
          </Button>
          <div className="flex-1" />
          <Button
            variant="outline"
            size="sm"
            className="text-red-500 hover:bg-red-50 hover:text-red-600"
            onClick={() => void onDelete()}
          >
            <Trash className="size-3.5" />
            删除数据源
          </Button>
        </div>
      </div>
    </FadeContent>
  )
}

