import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  Brain,
  ChatsTeardrop,
  Database,
  MagicWand,
  ShieldCheck,
  Sparkle,
  StackSimple,
} from '@phosphor-icons/react'
import { Link } from 'react-router-dom'

import type {
  AdminDatasourceProfile,
  AdminDatasourceSummary,
  AdminOnboardingRun,
  AdminSkillPackSummary,
} from '@/lib/api'
import {
  getAdminDatasourceProfile,
  listAdminDatasources,
  listAdminOnboardingRuns,
  listAdminSkillPacks,
} from '@/lib/api'
import FadeContent from '@/components/FadeContent'
import { NoticeBanner } from '@/components/layout/notice-banner'
import { PageIntro } from '@/components/layout/page-intro'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '暂无记录'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function analysisStatusLabel(value: string | null | undefined): string {
  if (!value) return 'pending'
  return value
}

const quickActions = [
  {
    to: '/workbench',
    title: '直接查询',
    detail: '进入实时工作台，发起多轮对话并检查 SQL。',
    icon: ChatsTeardrop,
  },
  {
    to: '/admin/datasources',
    title: '维护数据源',
    detail: '管理连接目录、默认数据源与结构快照。',
    icon: Database,
  },
  {
    to: '/admin/history',
    title: '分析工作区',
    detail: '进入单主线的 Onboarding Agent 工作区，查看过程并重跑分析。',
    icon: Brain,
  },
  {
    to: '/admin/history',
    title: '分析任务',
    detail: '查看数据源分析轨迹、补充业务上下文并重新生成技能包。',
    icon: MagicWand,
  },
] as const

export function OverviewPage() {
  const [datasources, setDatasources] = useState<AdminDatasourceSummary[]>([])
  const [profiles, setProfiles] = useState<Record<string, AdminDatasourceProfile | null>>({})
  const [recentRuns, setRecentRuns] = useState<AdminOnboardingRun[]>([])
  const [skillPacks, setSkillPacks] = useState<AdminSkillPackSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadOverview = useCallback(async () => {
    setLoading(true)
    try {
      const [nextDatasources, nextSkillPacks, nextRuns] = await Promise.all([
        listAdminDatasources(),
        listAdminSkillPacks(),
        listAdminOnboardingRuns(undefined, 6),
      ])

      const profileEntries = await Promise.all(
        nextDatasources.map(async (item) => {
          try {
            const profile = await getAdminDatasourceProfile(item.id)
            return [item.id, profile] as const
          } catch {
            return [item.id, null] as const
          }
        }),
      )

      setDatasources(nextDatasources)
      setSkillPacks(nextSkillPacks)
      setRecentRuns(nextRuns)
      setProfiles(Object.fromEntries(profileEntries))
      setError(null)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  const totals = useMemo(() => {
    const profileItems = Object.values(profiles).filter(Boolean)
    const successCount = recentRuns.filter((item) => item.status === 'completed').length
    return {
      datasourceCount: datasources.length,
      introspectedCount: datasources.filter((item) => item.last_introspected_at).length,
      activeSkillCount: skillPacks.filter((item) => item.status !== 'rejected').length,
      draftSkillCount: skillPacks.filter((item) => item.status === 'draft').length,
      activeMemoryCount: profileItems.reduce(
        (sum, item) => sum + (item?.active_memory_count ?? 0),
        0,
      ),
      recentSuccessRate: recentRuns.length
        ? Math.round((successCount / recentRuns.length) * 100)
        : 0,
    }
  }, [datasources, profiles, recentRuns, skillPacks])

  return (
    <div className="space-y-6">
      <PageIntro
        eyebrow="产品总览"
        title="系统状态与入口"
        description="查看数据源、技能、执行与审计的实时概览。"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void loadOverview()}>
              刷新
            </Button>
            <Button asChild variant="link" size="sm">
              <Link to="/workbench">
                打开工作台
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </>
        }
      />

      {error ? <NoticeBanner tone="danger">{error}</NoticeBanner> : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="关键指标">
        <FadeContent delay={0} duration={360}>
          <div className="rounded-[var(--radius-control)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] px-4 py-3">
            <div className="mb-2 flex items-center gap-2 text-[var(--primary)]">
              <Database className="size-4 shrink-0" aria-hidden />
            </div>
            <p className="text-2xl font-semibold tabular-nums text-[var(--foreground)]">
              {loading ? '—' : totals.datasourceCount}
            </p>
            <p className="text-[11px] text-[var(--muted-foreground)]">数据源数量</p>
          </div>
        </FadeContent>
        <FadeContent delay={80} duration={360}>
          <div className="rounded-[var(--radius-control)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] px-4 py-3">
            <div className="mb-2 flex items-center gap-2 text-[var(--primary)]">
              <Brain className="size-4 shrink-0" aria-hidden />
            </div>
            <p className="text-2xl font-semibold tabular-nums text-[var(--foreground)]">
              {loading ? '—' : totals.activeSkillCount}
            </p>
            <p className="text-[11px] text-[var(--muted-foreground)]">活跃技能包</p>
          </div>
        </FadeContent>
        <FadeContent delay={160} duration={360}>
          <div className="rounded-[var(--radius-control)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] px-4 py-3">
            <div className="mb-2 flex items-center gap-2 text-[var(--primary)]">
              <StackSimple className="size-4 shrink-0" aria-hidden />
            </div>
            <p className="text-2xl font-semibold tabular-nums text-[var(--foreground)]">
              {loading ? '—' : totals.activeMemoryCount}
            </p>
            <p className="text-[11px] text-[var(--muted-foreground)]">主记忆文档</p>
          </div>
        </FadeContent>
        <FadeContent delay={240} duration={360}>
          <div className="rounded-[var(--radius-control)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] px-4 py-3">
            <div className="mb-2 flex items-center gap-2 text-[var(--primary)]">
              <ShieldCheck className="size-4 shrink-0" aria-hidden />
            </div>
            <p className="text-2xl font-semibold tabular-nums text-[var(--foreground)]">
              {loading ? '—' : `${totals.recentSuccessRate}%`}
            </p>
            <p className="text-[11px] text-[var(--muted-foreground)]">最近成功率</p>
          </div>
        </FadeContent>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="快捷入口">
        {quickActions.map((item) => {
          const Icon = item.icon
          return (
            <Card key={item.to} className="surface-card-interactive border-[var(--line)]">
              <Link to={item.to} className="block h-full">
                <CardHeader className="gap-3 pb-4">
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex size-9 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--primary)]">
                      <Icon className="size-4" />
                    </span>
                    <ArrowRight className="mt-0.5 size-4 shrink-0 text-[var(--muted-foreground)]" />
                  </div>
                  <div className="space-y-1.5">
                    <CardTitle className="text-[15px] font-semibold leading-snug tracking-[-0.02em]">
                      {item.title}
                    </CardTitle>
                    <CardDescription className="text-[12px] leading-relaxed">
                      {item.detail}
                    </CardDescription>
                  </div>
                </CardHeader>
              </Link>
            </Card>
          )
        })}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.14fr)_minmax(320px,0.86fr)]">
        <Card className="rounded-[var(--radius-page)] border-[var(--line)]">
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="text-base font-semibold">数据源网络</CardTitle>
              <CardDescription className="text-[12px]">
                已接入数据源的基础状态、学习与结构采集概况。
              </CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link to="/admin/datasources">管理数据源</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <p className="text-[13px] text-[var(--foreground-soft)]">正在汇总数据源状态...</p>
            ) : datasources.length === 0 ? (
              <p className="text-[13px] text-[var(--foreground-soft)]">当前还没有已接入的数据源。</p>
            ) : (
              datasources.map((item) => {
                const profile = profiles[item.id]
                return (
                  <div
                    key={item.id}
                    className="rounded-[calc(var(--radius-card)-0.1rem)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] px-4 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                        {item.display_name}
                      </span>
                      {item.is_default ? <Badge className="text-[10px]">默认</Badge> : null}
                      <Badge variant="outline" className="text-[10px]">
                        {item.dialect}
                      </Badge>
                      <Badge variant="outline" className="text-[10px]">
                        {analysisStatusLabel(profile?.analysis_status)}
                      </Badge>
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-[var(--muted-foreground)]">{item.id}</p>
                    <p className="mt-2 text-[11px] leading-5 text-[var(--foreground-soft)]">
                      技能包 {profile?.skill_packs.length ?? 0} · 主记忆 {profile?.active_memory_count ?? 0}{' '}
                      · 对话摘要 {profile?.thread_summary_count ?? 0}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--foreground-soft)]">
                      <span>最近采集 {formatDateTime(item.last_introspected_at)}</span>
                      <Link
                        to={`/admin/datasources/${encodeURIComponent(item.id)}`}
                        className="inline-flex items-center gap-1 font-medium text-[var(--primary)]"
                      >
                        查看技能
                        <ArrowRight className="size-3" />
                      </Link>
                    </div>
                  </div>
                )
              })
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card className="rounded-[var(--radius-page)] border-[var(--line)]">
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div className="space-y-1">
                <CardTitle className="text-base font-semibold">最近执行</CardTitle>
                <CardDescription className="text-[12px]">
                  最近的数据源分析任务与当前阶段。
                </CardDescription>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link to="/admin/history">查看全部</Link>
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {recentRuns.length === 0 ? (
                <p className="text-[13px] text-[var(--foreground-soft)]">暂无分析记录。</p>
              ) : (
                recentRuns.slice(0, 4).map((item) => (
                  <div
                    key={item.id}
                    className="rounded-[calc(var(--radius-card)-0.12rem)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_80%,white)] px-4 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-semibold text-[var(--foreground)]">
                        分析任务
                      </span>
                      <Badge
                        variant={item.status === 'completed' ? 'default' : 'outline'}
                        className="text-[10px]"
                      >
                        {item.status}
                      </Badge>
                      {item.datasource_id ? (
                        <Badge variant="outline" className="text-[10px]">
                          {item.datasource_id}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-2 text-[11px] leading-5 text-[var(--muted-foreground)]">
                      {item.status_message}
                    </p>
                    <p className="mt-1.5 text-[11px] text-[var(--foreground-soft)]">
                      {item.started_at ? formatDateTime(item.started_at) : '暂无时间'}
                    </p>
                    {item.datasource_id ? (
                      <Link
                        to={`/admin/history?datasource_id=${encodeURIComponent(item.datasource_id)}&run_id=${encodeURIComponent(item.id)}`}
                        className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-[var(--primary)]"
                      >
                        查看这次分析
                        <ArrowRight className="size-3" />
                      </Link>
                    ) : null}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="rounded-[var(--radius-page)] border-[var(--line)]">
            <CardHeader className="space-y-1">
              <CardTitle className="text-base font-semibold">分析入口</CardTitle>
              <CardDescription className="text-[12px]">
                直接进入单主线的 Onboarding Agent 分析工作区。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-[13px] leading-relaxed text-[var(--foreground-soft)]">
                这里不再承载旧的“历史中心”语义。分析、澄清和技能预览都在新的分析工作区里完成。
              </p>
              <Button asChild variant="outline" size="sm">
                <Link to="/admin/history">打开分析工作区</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="产品能力">
        <Card className="rounded-[var(--radius-page)] border-[var(--line)]">
          <CardHeader className="space-y-2">
            <div className="flex items-center gap-2">
              <Sparkle className="size-4 shrink-0 text-[var(--primary)]" aria-hidden />
              <CardTitle className="text-base font-semibold">运行时学习</CardTitle>
            </div>
            <CardDescription className="text-[12px] leading-relaxed">
              记忆命中、历史命中、主记忆维护与技能草稿会随对话积累，形成持续进化的系统资产。
            </CardDescription>
          </CardHeader>
        </Card>

        <Card className="rounded-[var(--radius-page)] border-[var(--line)]">
          <CardHeader className="space-y-2">
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-4 shrink-0 text-[var(--primary)]" aria-hidden />
              <CardTitle className="text-base font-semibold">执行护栏</CardTitle>
            </div>
            <CardDescription className="text-[12px] leading-relaxed">
              查询经可检查的 SQL 草稿与只读守卫后，再进入真实数据源执行。
            </CardDescription>
          </CardHeader>
        </Card>

        <Card className="rounded-[var(--radius-page)] border-[var(--line)]">
          <CardHeader className="space-y-2">
            <div className="flex items-center gap-2">
              <StackSimple className="size-4 shrink-0 text-[var(--primary)]" aria-hidden />
              <CardTitle className="text-base font-semibold">跨模块联动</CardTitle>
            </div>
            <CardDescription className="text-[12px] leading-relaxed">
              数据源、技能工坊、工作台与历史页共享同一套后台能力，避免模块割裂。
            </CardDescription>
          </CardHeader>
        </Card>
      </section>
    </div>
  )
}
