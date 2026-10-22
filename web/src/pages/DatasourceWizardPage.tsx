import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  ArrowsClockwise,
  CheckCircle,
  Database,
  Lightning,
  MagnifyingGlass,
  Plugs,
  StackSimple,
  WarningCircle,
} from '@phosphor-icons/react'

import type {
  AdminDatasourceDetail,
  AdminDatasourceIntrospectResponse,
  AdminOnboardingRun,
  AdminDatasourceProfile,
  AdminSkillPackSummary,
  Dialect,
  DatasourceSchemaPayload,
} from '@/lib/api'
import {
  createAdminDatasource,
  getAdminDatasourceOnboardingRun,
  getAdminDatasourceProfile,
  getAdminDatasourceSchema,
  introspectAdminDatasource,
  listAdminSkillPacks,
  runAdminDatasourceOnboarding,
  testAdminDatasource,
} from '@/lib/api'
import FadeContent from '@/components/FadeContent'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

type WizardStep = 0 | 1 | 2 | 3

const STEPS = [
  { label: '连接配置', icon: Plugs },
  { label: '结构采集', icon: Database },
  { label: '智能分析', icon: MagnifyingGlass },
  { label: '技能预览', icon: StackSimple },
] as const

function onboardingPhaseLabel(phase: string | null | undefined): string {
  switch (phase) {
    case 'queued': return '排队中'
    case 'prepare': return '准备任务'
    case 'prepare_schema_snapshot': return '结构快照'
    case 'build_rich_profile': return '画像构建'
    case 'llm_analysis': return '模型分析'
    case 'llm_attempt': return '分析尝试'
    case 'llm_tool_call': return '工具调用'
    case 'llm_tool_result': return '工具结果'
    case 'llm_parse': return '结果整理'
    case 'persist_analysis': return '结果落库'
    case 'persist_skill_pack': return '写入技能包'
    case 'embedding_pack': return '包向量化'
    case 'embedding_document': return '文档向量化'
    case 'finalize': return '收尾'
    case 'complete': return '完成'
    case 'failed': return '失败'
    default: return phase || '处理中'
  }
}

export function DatasourceWizardPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<WizardStep>(0)

  const [dsId, setDsId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [dialect, setDialect] = useState<Dialect>('postgresql')
  const [connectionUrl, setConnectionUrl] = useState('')
  const [isDefault, setIsDefault] = useState(false)

  const [connMode, setConnMode] = useState<'fields' | 'url'>('fields')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [dbName, setDbName] = useState('')
  const [dbUser, setDbUser] = useState('')
  const [dbPass, setDbPass] = useState('')

  const buildUrlFromFields = () => {
    const h = host.trim() || 'localhost'
    const p = port.trim() || (dialect === 'postgresql' ? '5432' : '3306')
    const d = dbName.trim()
    const u = encodeURIComponent(dbUser.trim())
    const pw = encodeURIComponent(dbPass)
    const scheme = dialect === 'postgresql' ? 'postgresql+psycopg' : 'mysql+pymysql'
    return `${scheme}://${u}:${pw}@${h}:${p}/${d}`
  }

  const effectiveUrl = connMode === 'fields' ? buildUrlFromFields() : connectionUrl

  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [savedDetail, setSavedDetail] = useState<AdminDatasourceDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [introspecting, setIntrospecting] = useState(false)
  const [introspectResult, setIntrospectResult] = useState<AdminDatasourceIntrospectResponse | null>(null)
  const [schema, setSchema] = useState<DatasourceSchemaPayload | null>(null)

  const [analyzing, setAnalyzing] = useState(false)
  const [onboardingRun, setOnboardingRun] = useState<AdminOnboardingRun | null>(null)
  const [profile, setProfile] = useState<AdminDatasourceProfile | null>(null)

  const [skillPacks, setSkillPacks] = useState<AdminSkillPackSummary[]>([])

  const handleTest = useCallback(async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)
    try {
      const url = connMode === 'fields' ? buildUrlFromFields() : connectionUrl
      const result = await testAdminDatasource({ connection_url: url, dialect })
      setTestResult(result)
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : '连接测试失败' })
    } finally {
      setTesting(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionUrl, dialect, connMode, host, port, dbName, dbUser, dbPass])

  const handleSave = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      const url = connMode === 'fields' ? buildUrlFromFields() : connectionUrl
      const detail = await createAdminDatasource({
        id: dsId.trim(),
        display_name: displayName.trim(),
        dialect,
        connection_url: url,
        is_default: isDefault,
      })
      setSavedDetail(detail)
      setStep(1)

      setIntrospecting(true)
      try {
        const introResult = await introspectAdminDatasource(detail.id)
        setIntrospectResult(introResult)
        if (introResult.ok) {
          const schemaData = await getAdminDatasourceSchema(detail.id)
          setSchema(schemaData)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '结构采集失败')
      } finally {
        setIntrospecting(false)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dsId, displayName, dialect, connectionUrl, isDefault, connMode, host, port, dbName, dbUser, dbPass])

  const handleIntrospect = useCallback(async () => {
    if (!savedDetail) return
    setIntrospecting(true)
    setError(null)
    try {
      const result = await introspectAdminDatasource(savedDetail.id)
      setIntrospectResult(result)
      if (result.ok) {
        const schemaData = await getAdminDatasourceSchema(savedDetail.id)
        setSchema(schemaData)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '结构采集失败')
    } finally {
      setIntrospecting(false)
    }
  }, [savedDetail])

  const handleAnalyze = useCallback(async () => {
    if (!savedDetail) return
    setAnalyzing(true)
    setError(null)
    setStep(2)
    try {
      const run = await runAdminDatasourceOnboarding(savedDetail.id)
      setOnboardingRun(run)
    } catch (err) {
      setError(err instanceof Error ? err.message : '智能分析失败')
      try {
        const p = await getAdminDatasourceProfile(savedDetail.id)
        setProfile(p)
      } catch { /* ignore */ }
      } finally {
        setAnalyzing(false)
      }
  }, [savedDetail])

  useEffect(() => {
    if (step !== 2 || !savedDetail) return

    let cancelled = false
    let timer: number | undefined

    const pollRun = async () => {
      try {
        const run = await getAdminDatasourceOnboardingRun(savedDetail.id)
        if (cancelled) return
        if (!run) {
          if (!cancelled) {
            timer = window.setTimeout(pollRun, 1500)
          }
          return
        }
        setOnboardingRun(run)
        const active = run.status === 'queued' || run.status === 'running'
        setAnalyzing(active)

        if (run.status === 'completed') {
          const [nextProfile, packs] = await Promise.all([
            getAdminDatasourceProfile(savedDetail.id),
            listAdminSkillPacks(savedDetail.id),
          ])
          if (cancelled) return
          setProfile(nextProfile)
          setSkillPacks(packs)
          if (nextProfile.analysis_status === 'ready' || packs.length > 0) {
            setStep(3)
            return
          }
          return
        }

        if (run.status === 'failed') {
          setError(run.error ?? '智能分析失败')
          try {
            const nextProfile = await getAdminDatasourceProfile(savedDetail.id)
            if (!cancelled) setProfile(nextProfile)
          } catch {
            /* ignore */
          }
          return
        }
      } catch (err) {
        if (!cancelled) {
          setAnalyzing(false)
          setError(err instanceof Error ? err.message : '获取分析状态失败')
        }
        return
      }

      if (!cancelled) {
        timer = window.setTimeout(pollRun, 1500)
      }
    }

    void pollRun()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [savedDetail, step])

  const canSave = dsId.trim().length > 0 && (
    connMode === 'url'
      ? connectionUrl.trim().length > 0
      : host.trim().length > 0 && dbName.trim().length > 0
  )
  const canGoToAnalyze = introspectResult?.ok === true

  return (
    <div className="mx-auto max-w-3xl">
      <FadeContent duration={400}>
        <button
          type="button"
          onClick={() => navigate('/admin/datasources')}
          className="mb-6 flex items-center gap-1.5 text-xs font-medium text-[var(--foreground-soft)] transition-colors hover:text-[var(--foreground)]"
        >
          <ArrowLeft className="size-3.5" />
          返回数据源列表
        </button>
      </FadeContent>

      <FadeContent duration={400} delay={60}>
        <h1 className="text-xl font-semibold tracking-[-0.035em] text-[var(--foreground)]">
          新建数据源
        </h1>
        <p className="mt-1 text-[13px] text-[var(--foreground-soft)]">
          按步骤连接数据库、采集结构、生成智能技能包。
        </p>
      </FadeContent>

      {/* Stepper */}
      <FadeContent duration={400} delay={120}>
        <div className="mt-8 flex items-center gap-0">
          {STEPS.map((s, i) => {
            const Icon = s.icon
            const isCurrent = step === i
            const isDone = step > i
            return (
              <div key={s.label} className="flex flex-1 items-center">
                <div className="flex flex-col items-center gap-1.5">
                  <div
                    className={cn(
                      'flex size-9 items-center justify-center rounded-xl border transition-all duration-300',
                      isDone
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-600'
                        : isCurrent
                          ? 'border-[color-mix(in_srgb,var(--primary)_30%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--primary)]'
                          : 'border-[var(--line)] bg-[var(--surface-strong)] text-[var(--muted-foreground)]',
                    )}
                  >
                    {isDone ? <CheckCircle className="size-4" weight="fill" /> : <Icon className="size-4" />}
                  </div>
                  <span
                    className={cn(
                      'text-[11px] font-medium',
                      isCurrent ? 'text-[var(--foreground)]' : 'text-[var(--muted-foreground)]',
                    )}
                  >
                    {s.label}
                  </span>
                </div>
                {i < STEPS.length - 1 ? (
                  <div
                    className={cn(
                      'mx-2 h-px flex-1 transition-colors duration-300',
                      step > i ? 'bg-emerald-300' : 'bg-[var(--line)]',
                    )}
                  />
                ) : null}
              </div>
            )
          })}
        </div>
      </FadeContent>

      {error ? (
        <FadeContent duration={300}>
          <div className="mt-6 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
            <WarningCircle className="mt-0.5 size-4 shrink-0" weight="fill" />
            <span>{error}</span>
          </div>
        </FadeContent>
      ) : null}

      <div className="mt-8">
        {/* Step 0: Connection Config */}
        {step === 0 ? (
          <FadeContent duration={400}>
            <div className="space-y-5 rounded-[var(--radius-page)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-[var(--foreground)]">数据源 ID</label>
                  <Input
                    value={dsId}
                    onChange={(e) => setDsId(e.target.value)}
                    placeholder="my-postgres-db"
                    className="font-mono text-xs"
                  />
                  <p className="text-[10px] text-[var(--muted-foreground)]">唯一标识符，创建后不可修改</p>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-[var(--foreground)]">显示名称</label>
                  <Input
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="我的 PostgreSQL 数据库"
                    className="text-xs"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-[var(--foreground)]">数据库类型</label>
                <div className="flex gap-2">
                  {(['postgresql', 'mysql'] as Dialect[]).map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setDialect(d)}
                      className={cn(
                        'rounded-lg border px-4 py-2 text-xs font-medium transition-all duration-200',
                        dialect === d
                          ? 'border-[color-mix(in_srgb,var(--primary)_30%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_8%,white)] text-[var(--foreground)]'
                          : 'border-[var(--line)] text-[var(--foreground-soft)] hover:border-[var(--line-strong)]',
                      )}
                    >
                      {d === 'postgresql' ? 'PostgreSQL' : 'MySQL'}
                    </button>
                  ))}
                </div>
              </div>

              {/* Connection mode tabs */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-[var(--foreground)]">连接配置</label>
                  <div className="flex rounded-lg border border-[var(--line)] p-0.5">
                    {([
                      { key: 'fields' as const, label: '分字段输入' },
                      { key: 'url' as const, label: '连接串' },
                    ]).map((m) => (
                      <button
                        key={m.key}
                        type="button"
                        onClick={() => setConnMode(m.key)}
                        className={cn(
                          'rounded-md px-3 py-1 text-[11px] font-medium transition-all duration-200',
                          connMode === m.key
                            ? 'bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--foreground)]'
                            : 'text-[var(--foreground-soft)] hover:text-[var(--foreground)]',
                        )}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                </div>

                {connMode === 'fields' ? (
                  <div className="space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1">
                        <label className="text-[11px] text-[var(--foreground-soft)]">主机地址</label>
                        <Input
                          value={host}
                          onChange={(e) => setHost(e.target.value)}
                          placeholder="localhost 或 192.168.1.100"
                          className="font-mono text-xs"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[11px] text-[var(--foreground-soft)]">端口</label>
                        <Input
                          value={port}
                          onChange={(e) => setPort(e.target.value)}
                          placeholder={dialect === 'postgresql' ? '5432' : '3306'}
                          className="font-mono text-xs"
                        />
                      </div>
                    </div>
                    <div className="space-y-1">
                      <label className="text-[11px] text-[var(--foreground-soft)]">数据库名</label>
                      <Input
                        value={dbName}
                        onChange={(e) => setDbName(e.target.value)}
                        placeholder="my_database"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1">
                        <label className="text-[11px] text-[var(--foreground-soft)]">用户名</label>
                        <Input
                          value={dbUser}
                          onChange={(e) => setDbUser(e.target.value)}
                          placeholder="postgres"
                          className="font-mono text-xs"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[11px] text-[var(--foreground-soft)]">密码</label>
                        <Input
                          type="password"
                          value={dbPass}
                          onChange={(e) => setDbPass(e.target.value)}
                          placeholder="••••••••"
                          className="font-mono text-xs"
                        />
                      </div>
                    </div>
                    {host.trim() || dbName.trim() ? (
                      <p className="truncate rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 font-mono text-[11px] text-[var(--foreground-soft)]">
                        {effectiveUrl}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <Textarea
                    value={connectionUrl}
                    onChange={(e) => setConnectionUrl(e.target.value)}
                    placeholder={
                      dialect === 'postgresql'
                        ? 'postgresql+psycopg://user:pass@host:5432/dbname'
                        : 'mysql+pymysql://user:pass@host:3306/dbname'
                    }
                    className="min-h-[68px] resize-none font-mono text-xs"
                  />
                )}
              </div>

              <label className="flex items-center gap-2 text-xs text-[var(--foreground-soft)]">
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="size-3.5 rounded border-[var(--line)]"
                />
                设为默认数据源
              </label>

              <div className="flex items-center gap-3 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleTest()}
                  disabled={testing || !canSave}
                >
                  {testing ? <Spinner className="size-3.5" /> : <Plugs className="size-3.5" />}
                  测试连接
                </Button>
                <Button size="sm" onClick={() => void handleSave()} disabled={saving || !canSave}>
                  {saving ? <Spinner className="size-3.5" /> : <ArrowRight className="size-3.5" />}
                  保存并采集结构
                </Button>
              </div>

              {testResult ? (
                <div
                  className={cn(
                    'flex items-center gap-2 rounded-lg border px-3 py-2 text-xs',
                    testResult.ok
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-red-200 bg-red-50 text-red-700',
                  )}
                >
                  {testResult.ok ? (
                    <CheckCircle className="size-3.5" weight="fill" />
                  ) : (
                    <WarningCircle className="size-3.5" weight="fill" />
                  )}
                  {testResult.message}
                </div>
              ) : null}
            </div>
          </FadeContent>
        ) : null}

        {/* Step 1: Schema Introspection */}
        {step === 1 ? (
          <FadeContent duration={400}>
            <div className="space-y-5 rounded-[var(--radius-page)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
              {introspecting ? (
                <div className="flex flex-col items-center gap-3 py-10">
                  <Spinner className="size-6 text-[var(--primary)]" />
                  <p className="text-sm text-[var(--foreground-soft)]">正在采集数据库结构…</p>
                </div>
              ) : introspectResult?.ok ? (
                <>
                  <div className="flex items-center gap-2">
                    <CheckCircle className="size-5 text-emerald-500" weight="fill" />
                    <span className="text-sm font-medium text-[var(--foreground)]">结构采集完成</span>
                  </div>
                  <div className="flex flex-wrap gap-3 text-xs text-[var(--foreground-soft)]">
                    <span>{introspectResult.table_count} 个表</span>
                    <span>{introspectResult.column_count} 个字段</span>
                    {introspectResult.truncated ? (
                      <Badge variant="outline" className="h-5 px-1.5 text-[9px]">已截断</Badge>
                    ) : null}
                  </div>

                  {schema ? (
                    <div className="max-h-[320px] space-y-1 overflow-y-auto rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3">
                      {schema.tables.map((table) => (
                        <SchemaTableRow key={table.name} table={table} />
                      ))}
                    </div>
                  ) : null}

                  <div className="flex items-center gap-3 pt-2">
                    <Button variant="outline" size="sm" onClick={() => void handleIntrospect()}>
                      <ArrowsClockwise className="size-3.5" />
                      重新采集
                    </Button>
                    <Button size="sm" onClick={() => void handleAnalyze()} disabled={!canGoToAnalyze}>
                      <ArrowRight className="size-3.5" />
                      开始智能分析
                    </Button>
                  </div>
                </>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <WarningCircle className="size-4" weight="fill" />
                    结构采集失败
                  </div>
                  <p className="text-xs text-[var(--foreground-soft)]">{introspectResult?.message}</p>
                  <Button variant="outline" size="sm" onClick={() => void handleIntrospect()}>
                    重试
                  </Button>
                </div>
              )}
            </div>
          </FadeContent>
        ) : null}

        {/* Step 2: Analysis */}
        {step === 2 ? (
          <FadeContent duration={400}>
            <div className="space-y-5 rounded-[var(--radius-page)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
              {analyzing ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                    <Spinner className="size-5 text-[var(--primary)]" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[var(--foreground)]">
                        {onboardingRun?.status_message || '正在分析数据源结构并生成技能包…'}
                      </p>
                      <p className="text-[11px] text-[var(--muted-foreground)]">
                        当前阶段：{onboardingPhaseLabel(onboardingRun?.phase)}
                      </p>
                    </div>
                  </div>

                  {onboardingRun?.result_payload ? (
                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                        <p className="text-[10px] text-[var(--muted-foreground)]">分析状态</p>
                        <p className="mt-1 text-sm font-medium text-[var(--foreground)]">
                          {String(onboardingRun.result_payload.analysis_status ?? 'running')}
                        </p>
                      </div>
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                        <p className="text-[10px] text-[var(--muted-foreground)]">候选技能包</p>
                        <p className="mt-1 text-sm font-medium text-[var(--foreground)]">
                          {String(onboardingRun.result_payload.skill_pack_count ?? 0)}
                        </p>
                      </div>
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                        <p className="text-[10px] text-[var(--muted-foreground)]">待确认问题</p>
                        <p className="mt-1 text-sm font-medium text-[var(--foreground)]">
                          {String(onboardingRun.result_payload.unresolved_question_count ?? 0)}
                        </p>
                      </div>
                    </div>
                  ) : null}

                  {onboardingRun?.events?.length ? (
                    <div className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-[var(--foreground)]">运行轨迹</span>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => savedDetail && void getAdminDatasourceOnboardingRun(savedDetail.id).then(setOnboardingRun)}
                        >
                          <ArrowsClockwise className="size-3.5" />
                          刷新状态
                        </Button>
                      </div>
                      <div className="max-h-[280px] space-y-2 overflow-y-auto">
                        {onboardingRun.events.slice().reverse().map((event, index) => (
                          <div
                            key={`${event.timestamp}-${index}`}
                            className="rounded-lg border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_70%,white)] px-3 py-2"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-[11px] font-medium text-[var(--foreground)]">
                                {onboardingPhaseLabel(event.phase)}
                              </span>
                              <span className="text-[10px] text-[var(--muted-foreground)]">
                                {new Date(event.timestamp).toLocaleTimeString()}
                              </span>
                            </div>
                            <p className="mt-1 text-[11px] leading-5 text-[var(--foreground-soft)]">
                              {event.message}
                            </p>
                            {event.payload ? (
                              <pre className="mt-2 overflow-x-auto rounded-md bg-[var(--background)] px-2 py-1 font-mono text-[10px] text-[var(--muted-foreground)]">
                                {JSON.stringify(event.payload, null, 2)}
                              </pre>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : profile ? (
                <>
                  <div className="flex items-center gap-2">
                    {profile.analysis_status === 'ready' ? (
                      <CheckCircle className="size-5 text-emerald-500" weight="fill" />
                    ) : (
                      <WarningCircle className="size-5 text-amber-500" weight="fill" />
                    )}
                    <span className="text-sm font-medium text-[var(--foreground)]">
                      {profile.analysis_status === 'ready' ? '分析完成' : '分析结束（部分结果）'}
                    </span>
                  </div>
                  {profile.summary ? (
                    <p className="text-xs leading-5 text-[var(--foreground-soft)]">{profile.summary}</p>
                  ) : null}
                  {profile.analysis_error ? (
                    <p className="text-xs text-red-600">{profile.analysis_error}</p>
                  ) : null}
                  {onboardingRun?.events?.length ? (
                    <div className="max-h-[240px] space-y-2 overflow-y-auto rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
                      {onboardingRun.events.slice().reverse().map((event, index) => (
                        <div key={`${event.timestamp}-${index}`} className="rounded-lg border border-[var(--line)] px-3 py-2">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-[11px] font-medium text-[var(--foreground)]">
                              {onboardingPhaseLabel(event.phase)}
                            </span>
                            <span className="text-[10px] text-[var(--muted-foreground)]">
                              {new Date(event.timestamp).toLocaleTimeString()}
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] leading-5 text-[var(--foreground-soft)]">{event.message}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  <div className="flex items-center gap-3 pt-2">
                    <Button size="sm" onClick={() => void handleAnalyze()}>
                      <ArrowsClockwise className="size-3.5" />
                      重新分析
                    </Button>
                    {savedDetail ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/admin/datasources/${encodeURIComponent(savedDetail.id)}`)}
                      >
                        <Database className="size-3.5" />
                        打开数据源详情
                      </Button>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>
          </FadeContent>
        ) : null}

        {/* Step 3: Skill Preview */}
        {step === 3 ? (
          <FadeContent duration={400}>
            <div className="space-y-5 rounded-[var(--radius-page)] border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
              <div className="flex items-center gap-2">
                <StackSimple className="size-5 text-[var(--primary)]" />
                <span className="text-sm font-medium text-[var(--foreground)]">
                  生成了 {skillPacks.length} 个技能包
                </span>
              </div>

              {skillPacks.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {skillPacks.map((pack) => (
                    <div
                      key={pack.id}
                      className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 transition-all duration-200 hover:border-[var(--line-strong)]"
                    >
                      <div className="flex items-center gap-2">
                        <h4 className="text-xs font-semibold text-[var(--foreground)]">{pack.name}</h4>
                        <Badge
                          variant={pack.status === 'ready' ? 'default' : 'outline'}
                          className="h-5 px-1.5 text-[9px]"
                        >
                          {pack.status === 'ready' ? '就绪' : '草稿'}
                        </Badge>
                      </div>
                      <p className="mt-1.5 line-clamp-2 text-[11px] leading-4 text-[var(--foreground-soft)]">
                        {pack.summary}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[var(--foreground-soft)]">暂未生成技能包。</p>
              )}

              <div className="flex items-center gap-3 pt-2">
                <Button
                  size="sm"
                  onClick={() => {
                    if (savedDetail) {
                      navigate(`/admin/datasources/${encodeURIComponent(savedDetail.id)}`)
                    }
                  }}
                >
                  <Lightning className="size-3.5" />
                  进入数据源详情
                </Button>
              </div>
            </div>
          </FadeContent>
        ) : null}
      </div>
    </div>
  )
}

function SchemaTableRow({
  table,
}: {
  table: {
    name: string
    comment?: string | null
    columns: Array<{ name: string; type: string; nullable: boolean; comment?: string | null }>
  }
}) {
  const [open, setOpen] = useState(false)

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-[color-mix(in_srgb,var(--surface-strong)_60%,white)]"
      >
        <Database className="size-3 shrink-0 text-[var(--primary)]" />
        <span className="min-w-0 flex-1">
          <span className="block font-mono font-medium text-[var(--foreground)]">{table.name}</span>
          {table.comment ? (
            <span className="block truncate text-[10px] text-[var(--foreground-soft)]">{table.comment}</span>
          ) : null}
        </span>
        <span className="text-[10px] text-[var(--muted-foreground)]">{table.columns.length} 列</span>
      </button>
      {open ? (
        <div className="ml-7 space-y-0.5 pb-1">
          {table.columns.map((col) => (
            <div key={col.name} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-start gap-2 px-2 py-1 text-[11px]">
              <span className="font-mono text-[var(--foreground-soft)]">{col.name}</span>
              <Badge variant="outline" className="h-4 px-1 text-[8px]">{col.type}</Badge>
              {col.nullable ? (
                <span className="text-[9px] text-[var(--muted-foreground)]">nullable</span>
              ) : null}
              {col.comment ? (
                <span className="col-span-3 text-[10px] leading-relaxed text-[var(--muted-foreground)]">
                  {col.comment}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
