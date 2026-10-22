import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowsClockwise,
  CaretRight,
  Database,
  MagicWand,
  PaperPlaneTilt,
  Sparkle,
  WarningCircle,
} from '@phosphor-icons/react'
import { useSearchParams } from 'react-router-dom'

import type {
  AdminAnalysisWorkspace,
  AdminDatasourceSummary,
  OnboardingChatEvent,
} from '@/lib/api'
import {
  getAdminDatasourceAnalysisWorkspace,
  listAdminDatasources,
  runAdminDatasourceOnboarding,
  streamDatasourceOnboardingChat,
} from '@/lib/api'
import { NoticeBanner } from '@/components/layout/notice-banner'
import { PageIntro } from '@/components/layout/page-intro'
import { ProductEmptyState } from '@/components/layout/product-empty-state'
import { ProductSelect } from '@/components/layout/product-select'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

function phaseLabel(phase: string | null | undefined): string {
  switch (phase) {
    case 'queued': return '排队中'
    case 'prepare': return '准备任务'
    case 'prepare_schema_snapshot': return '结构快照'
    case 'build_rich_profile': return '画像构建'
    case 'llm_analysis': return '模型分析'
    case 'llm_attempt': return '分析尝试'
    case 'llm_reasoning': return '推理摘要'
    case 'llm_tool_call': return '工具调用'
    case 'llm_tool_result': return '工具结果'
    case 'llm_parse': return '结果整理'
    case 'persist_analysis': return '分析落库'
    case 'persist_skill_pack': return '写入技能包'
    case 'embedding_pack': return '技能包向量化'
    case 'embedding_document': return '文档向量化'
    case 'finalize': return '完成收尾'
    case 'complete': return '完成'
    case 'failed': return '失败'
    case 'waiting_for_clarification': return '等待澄清'
    case 'resuming': return '继续分析'
    default: return phase || '处理中'
  }
}

function eventDetail(item: Extract<FeedItem, { kind: 'event' }>): string | null {
  const payload = item.payload
  if (!payload) return null
  if (item.phase === 'llm_reasoning' && typeof payload.text === 'string') {
    return payload.text
  }
  if (item.phase === 'llm_tool_call' && typeof payload.tool === 'string') {
    const argsPreview = typeof payload.args_preview === 'string' ? payload.args_preview : ''
    return argsPreview ? `${payload.tool}\n参数: ${argsPreview}` : `调用工具：${payload.tool}`
  }
  if (item.phase === 'llm_tool_result' && typeof payload.tool === 'string') {
    const preview = typeof payload.preview === 'string' ? payload.preview : ''
    return preview ? `${payload.tool}\n结果: ${preview}` : `工具结果：${payload.tool}`
  }
  if (item.phase === 'llm_attempt_failed' && typeof payload.error === 'string') {
    return payload.error
  }
  return null
}

type FeedItem =
  | { kind: 'event'; id: string; phase: string; message: string; timestamp: string; payload?: Record<string, unknown> | null }
  | { kind: 'message'; id: string; role: 'assistant' | 'user'; content: string; timestamp: string }
  | { kind: 'clarification'; id: string; prompt: string; reason: string; inputKind: string; options: string[]; timestamp: string }
  | { kind: 'result'; id: string; resultPreview: Record<string, unknown>; timestamp: string }

function buildFeed(workspace: AdminAnalysisWorkspace | null): FeedItem[] {
  if (!workspace) return []
  const items: FeedItem[] = []
  for (const event of workspace.timeline_items) {
    items.push({
      kind: 'event',
      id: `event:${event.timestamp}:${event.phase}:${event.message}`,
      phase: event.phase,
      message: event.message,
      timestamp: event.timestamp,
      payload: event.payload ?? null,
    })
  }
  for (const entry of workspace.conversation) {
    if (!entry || typeof entry !== 'object') continue
    const role = entry.role === 'user' ? 'user' : 'assistant'
    const content = typeof entry.content === 'string' ? entry.content : ''
    const timestamp = typeof entry.timestamp === 'string' ? entry.timestamp : ''
    if (!content.trim()) continue
    items.push({
      kind: 'message',
      id: `msg:${role}:${content.slice(0, 24)}:${items.length}`,
      role,
      content,
      timestamp,
    })
  }
  if (workspace.clarification) {
    const latestConversation = [...workspace.conversation].reverse().find((entry) => entry?.role === 'assistant' && typeof entry.timestamp === 'string')
    items.push({
      kind: 'clarification',
      id: `clarification:${workspace.clarification.prompt}`,
      prompt: workspace.clarification.prompt,
      reason: workspace.clarification.reason,
      inputKind: workspace.clarification.input_kind,
      options: workspace.clarification.options,
      timestamp: typeof latestConversation?.timestamp === 'string' ? latestConversation.timestamp : '',
    })
  }
  if (workspace.result_preview) {
    const selectedHistory = workspace.history.find((item) => item.run_id === workspace.selected_run_id)
    items.push({
      kind: 'result',
      id: `result:${workspace.selected_run_id ?? 'latest'}`,
      resultPreview: workspace.result_preview,
      timestamp: selectedHistory?.completed_at ?? selectedHistory?.started_at ?? '',
    })
  }
  return items.sort((left, right) => {
    const a = left.timestamp ? new Date(left.timestamp).getTime() : 0
    const b = right.timestamp ? new Date(right.timestamp).getTime() : 0
    return a - b
  })
}

export function AdminHistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [datasources, setDatasources] = useState<AdminDatasourceSummary[]>([])
  const [selectedDatasourceId, setSelectedDatasourceId] = useState('')
  const [pinnedRunId, setPinnedRunId] = useState<string | null>(null)
  const [workspace, setWorkspace] = useState<AdminAnalysisWorkspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [running, setRunning] = useState(false)
  const [chatBusy, setChatBusy] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const hasLoadedWorkspaceRef = useRef(false)

  const feedItems = useMemo(() => buildFeed(workspace), [workspace])
  const selectedHistoryItem = useMemo(
    () => workspace?.history.find((item) => item.run_id === workspace.selected_run_id) ?? null,
    [workspace],
  )

  const refreshDatasources = useCallback(async () => {
    const items = await listAdminDatasources()
    const preferredDatasourceId = searchParams.get('datasource_id')?.trim() || ''
    const preferredRunId = searchParams.get('run_id')?.trim() || ''
    setDatasources(items)
    setSelectedDatasourceId((current) => {
      if (preferredDatasourceId && items.some((item) => item.id === preferredDatasourceId)) return preferredDatasourceId
      if (current && items.some((item) => item.id === current)) return current
      return items[0]?.id ?? ''
    })
    if (preferredRunId) setPinnedRunId(preferredRunId)
  }, [searchParams])

  const loadWorkspace = useCallback(async (datasourceId: string, runId?: string | null) => {
    const firstLoad = !hasLoadedWorkspaceRef.current
    if (firstLoad) setLoading(true)
    else setRefreshing(true)
    try {
      const next = await getAdminDatasourceAnalysisWorkspace(datasourceId, runId ?? undefined)
      setWorkspace(next)
      hasLoadedWorkspaceRef.current = true
      setPinnedRunId(next.selected_run_id)
      setError(null)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      if (firstLoad) setLoading(false)
      else setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (!selectedDatasourceId) return
    const next = new URLSearchParams(searchParams)
    next.set('datasource_id', selectedDatasourceId)
    if (pinnedRunId) next.set('run_id', pinnedRunId)
    else next.delete('run_id')
    setSearchParams(next, { replace: true })
  }, [pinnedRunId, searchParams, selectedDatasourceId, setSearchParams])

  useEffect(() => {
    void refreshDatasources().catch((nextError) => {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    })
  }, [refreshDatasources])

  useEffect(() => {
    if (!selectedDatasourceId) return
    hasLoadedWorkspaceRef.current = false
    void loadWorkspace(selectedDatasourceId, pinnedRunId)
  }, [loadWorkspace, pinnedRunId, selectedDatasourceId])

  useEffect(() => {
    if (!workspace?.active_run || !workspace.selected_run_id) return
    if (workspace.active_run.id !== workspace.selected_run_id) return
    if (!['queued', 'running', 'waiting_for_clarification', 'resuming'].includes(workspace.active_run.status)) return

    const timer = window.setInterval(() => {
      void loadWorkspace(selectedDatasourceId, pinnedRunId)
    }, 1500)

    return () => window.clearInterval(timer)
  }, [loadWorkspace, pinnedRunId, selectedDatasourceId, workspace?.active_run, workspace?.selected_run_id])

  const startAnalysis = useCallback(async () => {
    if (!selectedDatasourceId) return
    setRunning(true)
    setNotice(null)
    setError(null)
    try {
      const run = await runAdminDatasourceOnboarding(selectedDatasourceId)
      setPinnedRunId(run.id)
      setNotice('已在后台启动分析。')
      await loadWorkspace(selectedDatasourceId, run.id)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setRunning(false)
    }
  }, [loadWorkspace, selectedDatasourceId])

  const sendChatMessage = useCallback(async (message?: string) => {
    if (!selectedDatasourceId) return
    const content = (message ?? chatInput).trim()
    if (!content && !workspace?.clarification) return

    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setChatBusy(true)
    setNotice(null)
    setError(null)
    try {
      await streamDatasourceOnboardingChat(
        selectedDatasourceId,
        { message: content || undefined, run_id: pinnedRunId },
        (event: OnboardingChatEvent) => {
          if (event.event === 'done' && event.data.should_rerun_analysis) {
            setNotice('当前信息已经足够，可以重新开始分析。')
          }
        },
        abortRef.current.signal,
      )
      setChatInput('')
      await loadWorkspace(selectedDatasourceId, pinnedRunId)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setChatBusy(false)
    }
  }, [chatInput, loadWorkspace, pinnedRunId, selectedDatasourceId, workspace?.clarification])

  const datasourceOptions = useMemo(
    () =>
      datasources.map((item) => ({
        value: item.id,
        label: item.display_name || item.id,
        description: item.id,
      })),
    [datasources],
  )

  return (
    <div className="space-y-6">
      <PageIntro
        eyebrow="Onboarding Agent"
        title="数据源智能分析"
        description="选择数据源后启动 Agent 自主分析。必要时，澄清问题会直接插入过程流。"
        actions={
          <>
            <ProductSelect
              value={selectedDatasourceId}
              options={datasourceOptions}
              placeholder="选择数据源"
              onChange={(value) => {
                setSelectedDatasourceId(value)
                setPinnedRunId(null)
              }}
              className="w-[220px]"
            />
            <Button variant="outline" size="sm" onClick={() => selectedDatasourceId && void loadWorkspace(selectedDatasourceId, pinnedRunId)}>
              <ArrowsClockwise className="size-3.5" />
              刷新
            </Button>
            <Button size="sm" disabled={!selectedDatasourceId || running} onClick={() => void startAnalysis()}>
              {running ? <Spinner className="size-3.5" /> : <MagicWand className="size-3.5" />}
              开始分析
            </Button>
          </>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="danger">{error}</NoticeBanner> : null}

      <div className="rounded-[1.8rem] border border-[color-mix(in_srgb,var(--line)_82%,white)] bg-white/62 p-5 shadow-[0_16px_44px_rgba(17,24,39,0.05),inset_0_1px_0_rgba(255,255,255,0.62)] backdrop-blur-xl">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-[var(--foreground)]">Agent 过程流</div>
                <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                  默认由 Agent 自主探索；只有关键缺口才会在过程流中插入澄清问题。
                </p>
              </div>
              <div className="flex items-center gap-2">
                {refreshing ? <Spinner className="size-3.5 text-[var(--muted-foreground)]" /> : null}
                {selectedHistoryItem ? <Badge variant="outline">{selectedHistoryItem.status}</Badge> : null}
              </div>
            </div>

          <div className="mt-4 space-y-3">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Spinner className="size-5" />
              </div>
            ) : feedItems.length === 0 ? (
              <ProductEmptyState
                icon={MagicWand}
                title="尚未开始分析"
                description="选择数据源后启动智能分析，这里会持续展示 Agent 的过程流和结果预览。"
                className="py-12"
              />
            ) : (
              feedItems.map((item) => {
                if (item.kind === 'event') {
                  const detail = eventDetail(item)
                  const payloadForDebug =
                    item.phase === 'llm_tool_result' && item.payload && typeof item.payload.result === 'object'
                      ? item.payload.result
                      : item.payload
                  return (
                    <div key={item.id} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-xs font-medium text-[var(--foreground)]">{phaseLabel(item.phase)}</span>
                        <span className="text-[10px] text-[var(--muted-foreground)]">
                          {new Date(item.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] leading-5 text-[var(--foreground-soft)]">{item.message}</p>
                      {detail ? (
                        <pre className="mt-2 overflow-x-auto rounded-md bg-[var(--background)] px-2 py-1 font-mono text-[10px] text-[var(--muted-foreground)]">
                          {detail}
                        </pre>
                      ) : null}
                      {payloadForDebug && !['llm_reasoning', 'llm_tool_call', 'llm_attempt_failed'].includes(item.phase) ? (
                        <pre className="mt-2 overflow-x-auto rounded-md bg-[var(--background)] px-2 py-1 font-mono text-[10px] text-[var(--muted-foreground)]">
                          {JSON.stringify(payloadForDebug, null, 2)}
                        </pre>
                      ) : null}
                    </div>
                  )
                }
                if (item.kind === 'message') {
                  return (
                    <div key={item.id} className={cn('flex gap-3', item.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
                      <div className={cn(
                        'flex size-7 shrink-0 items-center justify-center rounded-lg',
                        item.role === 'user'
                          ? 'bg-[color-mix(in_srgb,var(--primary)_12%,white)] text-[var(--primary)]'
                          : 'bg-[color-mix(in_srgb,var(--foreground)_6%,white)] text-[var(--foreground-soft)]',
                      )}>
                        {item.role === 'user' ? <Database className="size-3.5" /> : <Sparkle className="size-3.5" weight="duotone" />}
                      </div>
                      <div className={cn(
                        'max-w-[82%] rounded-xl px-3.5 py-2.5 text-xs leading-5',
                        item.role === 'user'
                          ? 'bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--foreground)]'
                          : 'border border-[var(--line)] bg-white text-[var(--foreground)]',
                      )}>
                        {item.content}
                      </div>
                    </div>
                  )
                }
                if (item.kind === 'clarification') {
                  return (
                    <div key={item.id} className="rounded-xl border border-[color-mix(in_srgb,var(--primary)_24%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_6%,white)] p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-[var(--foreground)]">
                        <WarningCircle className="size-4 text-[var(--primary)]" weight="fill" />
                        需要你补充一个关键问题
                      </div>
                      <p className="mt-2 text-sm text-[var(--foreground)]">{item.prompt}</p>
                      {item.reason ? (
                        <p className="mt-1 text-[11px] text-[var(--muted-foreground)]">{item.reason}</p>
                      ) : null}
                      {item.inputKind === 'single_select' && item.options.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {item.options.map((option) => (
                            <button
                              key={option}
                              type="button"
                              onClick={() => void sendChatMessage(option)}
                              className="rounded-full border border-[var(--line)] bg-white px-3 py-1.5 text-[11px] hover:border-[var(--line-strong)]"
                              disabled={chatBusy}
                            >
                              {option}
                            </button>
                          ))}
                        </div>
                      ) : item.inputKind === 'multi_select' && item.options.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {item.options.map((option) => {
                            const selected = chatInput.split('；').map((value) => value.trim()).filter(Boolean).includes(option)
                            return (
                              <button
                                key={option}
                                type="button"
                                onClick={() => setChatInput((current) => {
                                  const currentValues = current.split('；').map((value) => value.trim()).filter(Boolean)
                                  const nextValues = currentValues.includes(option)
                                    ? currentValues.filter((value) => value !== option)
                                    : [...currentValues, option]
                                  return nextValues.join('；')
                                })}
                                className={cn(
                                  'rounded-full border px-3 py-1.5 text-[11px]',
                                  selected
                                    ? 'border-[color-mix(in_srgb,var(--primary)_24%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_8%,white)]'
                                    : 'border-[var(--line)] bg-white',
                                )}
                                disabled={chatBusy}
                              >
                                {option}
                              </button>
                            )
                          })}
                        </div>
                      ) : null}
                      {item.inputKind === 'text' || item.inputKind === 'multi_select' ? (
                        <div className="mt-3 flex gap-2">
                          <Textarea
                            value={chatInput}
                            onChange={(event) => setChatInput(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' && !event.shiftKey) {
                                event.preventDefault()
                                void sendChatMessage()
                              }
                            }}
                            className="min-h-[44px] max-h-[120px] resize-none text-xs"
                            placeholder="补充这个关键问题的答案…"
                            disabled={chatBusy || !selectedDatasourceId}
                          />
                          <Button
                            size="sm"
                            className="h-11 px-3"
                            disabled={chatBusy || !selectedDatasourceId || !chatInput.trim()}
                            onClick={() => void sendChatMessage()}
                          >
                            {chatBusy ? <Spinner className="size-3.5" /> : <PaperPlaneTilt className="size-3.5" />}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  )
                }
                return (
                  <div key={item.id} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
                    <div className="flex items-center gap-2 text-xs font-medium text-[var(--foreground)]">
                      <CaretRight className="size-3.5 text-[var(--primary)]" weight="fill" />
                      本次分析结果预览
                    </div>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      {Array.isArray(item.resultPreview.preview_items) && item.resultPreview.preview_items.length > 0 ? (
                        item.resultPreview.preview_items.map((preview, index) => (
                          <div key={`${index}`} className="rounded-xl border border-[var(--line)] bg-white p-4">
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <p className="text-sm font-medium text-[var(--foreground)]">{String((preview as Record<string, unknown>).name ?? '未命名技能')}</p>
                                <p className="mt-1 text-[11px] text-[var(--muted-foreground)]">{String((preview as Record<string, unknown>).summary ?? '')}</p>
                              </div>
                              <Badge variant="outline">{String((preview as Record<string, unknown>).status ?? 'draft')}</Badge>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-[var(--muted-foreground)]">本次运行暂未生成可预览的技能。</div>
                      )}
                    </div>
                  </div>
                )
              })
            )}

          </div>
        </div>

    </div>
  )
}
