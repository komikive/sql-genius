import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowsClockwise,
  CaretDown,
  CaretRight,
  ChatText,
  CircleNotch,
  Clock,
  PaperPlaneTilt,
  PencilSimple,
  Play,
  SidebarSimple,
  Sparkle,
  ThumbsDown,
  ThumbsUp,
  Trash,
} from '@phosphor-icons/react'

import type {
  AdminSessionSummary,
  ChatStreamEvent,
  DatasourceOption,
  ExecuteResponse,
  ThreadTurnItem,
} from '@/lib/api'
import {
  fetchSuggestions,
  fetchThreadTurns,
  listAdminSessions,
  listDatasources,
  runSql,
  streamChat,
  submitTurnFeedback,
  deleteAdminSession,
} from '@/lib/api'
import { ProductSelect } from '@/components/layout/product-select'
import FadeContent from '@/components/FadeContent'
import { MessageResponse } from '@/components/ai-elements/message'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ResultTable } from '@/components/workbench/ResultTable'
import { SqlBlock } from '@/components/workbench/SqlBlock'
import { cn } from '@/lib/utils'
import {
  evidenceBadgeLabel,
  memoryBadgeLabel,
  sourceCategoryLabel,
} from '@/lib/semanticLabels'
import {
  buildAssistantSummary,
  formatStepDetail,
  mergeStepIntoRun,
  mergeUpdateIntoRun,
  parseInterruptPayload,
  sourcesFromUpdateData,
  type InterruptPayload,
  type RunAccumulator,
  type SourceItem,
  type StepPayload,
} from '@/lib/streamParse'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sql?: string
  timeline?: TimelineRow[]
  sources?: SourceItem[]
  memoryTitles?: string[]
  explanation?: string
  turnId?: number
  feedbackRating?: 'positive' | 'negative' | null
  streaming?: boolean
}

type TimelineRow = {
  id: string
  event: string
  label: string
  detail?: string
  stepId?: string
  payload?: StepPayload
}

function createEmptyRun(): RunAccumulator {
  return {
    sql: null,
    explanation: null,
    sqlError: null,
    responseText: null,
    recalledMemoryTitles: [],
    threadSummaryStatus: null,
    recentTurnCount: 0,
  }
}

function stepNameLabel(name: string): string {
  const labels: Record<string, string> = {
    prepare_context: '🧭 上下文准备',
    load_thread_summary: '🧵 线程摘要',
    load_datasource_memory: '🧠 数据源记忆',
    activate_skills: '📚 技能激活',
    retrieve_knowledge: '🔎 证据检索',
    generate_sql: '🧾 SQL 生成',
    validate_sql: '🛡️ SQL 校验',
    execute_sql: '▶️ SQL 执行',
    autonomous_agent: '🤖 Agent 执行',
    agent_loop: '🌀 自主规划',
    tool_call: '🔧 工具调用',
    reasoning_note: '💭 推理摘要',
    assistant_message: '✍️ 生成回答',
    memory_autoupdate: '📝 主记忆维护',
    clarification: '❓ 补充信息',
    budget_warning: '⏳ 预算提醒',
    complete: '✅ 完成',
  }
  return labels[name] ?? name.replace(/_/g, ' ')
}

function phaseLabel(phase: string): string {
  const labels: Record<string, string> = {
    start: '🚀 开始',
    complete: '✅ 完成',
    error: '⚠️ 错误',
    note: '🗒️ 说明',
    warning: '⏳ 警告',
    budget_exhausted: '🪫 预算耗尽',
  }
  return labels[phase] ?? phase
}

function summarizeEvent(event: ChatStreamEvent): TimelineRow | null {
  if (event.event === 'done') return null
  if (event.event === 'step') {
    const payload = event.data as StepPayload
    const name =
      typeof payload?.step_id === 'string'
        ? payload.step_id
        : typeof payload?.name === 'string'
          ? payload.name
          : 'step'
    const phase = typeof payload?.phase === 'string' ? payload.phase : ''
    const formatted = formatStepDetail(payload)
    const fallback =
      payload?.payload !== undefined ? JSON.stringify(payload.payload).slice(0, 280) : undefined
    return {
      id: crypto.randomUUID(),
      event: 'step',
      label: phase ? `${stepNameLabel(name)} · ${phaseLabel(phase)}` : stepNameLabel(name),
      detail: formatted ?? fallback,
      stepId: name,
      payload,
    }
  }
  if (event.event === 'interrupt') {
    const payload = parseInterruptPayload(event.data)
    return {
      id: crypto.randomUUID(),
      event: 'interrupt',
      label: '🙋 等待补充信息',
      detail: payload?.prompt ?? String(event.data),
    }
  }
  if (event.event === 'update') {
    return null
  }
  return null
}

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  return `${days} 天前`
}

function messageFromThreadTurn(turn: ThreadTurnItem): ChatMessage {
  const meta = turn.turn_metadata && typeof turn.turn_metadata === 'object'
    ? turn.turn_metadata
    : null

  const traceSteps = Array.isArray(meta?.trace_steps) ? meta.trace_steps : []
  const timeline = traceSteps
    .map((step) => summarizeEvent({ event: 'step', data: step }))
    .filter((row): row is TimelineRow => Boolean(row))

  const memoryTitles = Array.isArray(meta?.recalled_memory_titles)
    ? meta.recalled_memory_titles.filter((item): item is string => typeof item === 'string')
    : undefined

  return {
    id: String(turn.id),
    role: turn.role as 'user' | 'assistant',
    content: turn.content,
    sql: typeof meta?.generated_sql === 'string' ? meta.generated_sql : undefined,
    explanation: typeof meta?.sql_explanation === 'string' ? meta.sql_explanation : undefined,
    timeline: timeline.length > 0 ? timeline : undefined,
    memoryTitles: memoryTitles && memoryTitles.length > 0 ? memoryTitles : undefined,
    turnId: turn.id,
  }
}

export function WorkbenchShell() {
  const [threadId, setThreadId] = useState<string>(() => crypto.randomUUID())
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pendingTimeline, setPendingTimeline] = useState<TimelineRow[]>([])
  const [pendingSources, setPendingSources] = useState<SourceItem[]>([])
  const [liveRun, setLiveRun] = useState<RunAccumulator>(createEmptyRun())
  const [interruptPayload, setInterruptPayload] = useState<InterruptPayload | null>(null)
  const [busy, setBusy] = useState(false)
  const [selectedDatasourceId, setSelectedDatasourceId] = useState('')
  const [lockedDatasourceId, setLockedDatasourceId] = useState<string | null>(null)
  const [datasourceOptions, setDatasourceOptions] = useState<DatasourceOption[]>([])
  const [datasourceLoading, setDatasourceLoading] = useState(true)

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sessions, setSessions] = useState<AdminSessionSummary[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)

  const [suggestions, setSuggestions] = useState<string[]>([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const suggestionsCache = useRef<Record<string, string[]>>({})

  const runAccRef = useRef<RunAccumulator>(createEmptyRun())
  const pendingTimelineRef = useRef<TimelineRow[]>([])
  const pendingSourcesRef = useRef<SourceItem[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const syncRunState = useCallback((next: RunAccumulator) => {
    runAccRef.current = next
    setLiveRun(next)
  }, [])

  const effectiveDatasourceId = lockedDatasourceId ?? selectedDatasourceId
  const datasourceLocked = lockedDatasourceId !== null || messages.length > 0

  const datasourceSelectOptions = useMemo(
    () =>
      datasourceOptions.map((item) => ({
        value: item.id,
        label: item.label,
        description: item.dialect ? String(item.dialect) : item.id,
      })),
    [datasourceOptions],
  )

  const handleDatasourceChange = useCallback(
    (nextId: string) => {
      if (datasourceLocked || busy || !nextId || nextId === selectedDatasourceId) return
      setSelectedDatasourceId(nextId)
    },
    [busy, datasourceLocked, selectedDatasourceId],
  )

  // Load datasources
  useEffect(() => {
    let cancelled = false
    setDatasourceLoading(true)
    void listDatasources()
      .then((items) => {
        if (cancelled) return
        setDatasourceOptions(items)
        setSelectedDatasourceId((current) => {
          if (items.some((i) => i.id === current)) return current
          return items.find((i) => i.is_default)?.id ?? items[0]?.id ?? current
        })
      })
      .finally(() => {
        if (!cancelled) setDatasourceLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  // Load sessions for sidebar
  const refreshSessions = useCallback(() => {
    setSessionsLoading(true)
    void listAdminSessions(20, 0)
      .then(setSessions)
      .finally(() => setSessionsLoading(false))
  }, [])

  useEffect(() => { refreshSessions() }, [refreshSessions])

  // Load suggestions when datasource changes
  useEffect(() => {
    const id = effectiveDatasourceId
    if (suggestionsCache.current[id]) {
      setSuggestions(suggestionsCache.current[id])
      return
    }
    setSuggestionsLoading(true)
    void fetchSuggestions(id, 4)
      .then((payload) => {
        const items = Array.isArray(payload.items) ? payload.items : []
        if (!payload.is_fallback) {
          suggestionsCache.current[id] = items
        }
        setSuggestions(items)
      })
      .catch(() => setSuggestions([]))
      .finally(() => setSuggestionsLoading(false))
  }, [effectiveDatasourceId])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, busy, pendingTimeline.length, pendingSources.length, liveRun.responseText, liveRun.sql])

  const resetThread = useCallback(() => {
    abortRef.current?.abort()
    pendingTimelineRef.current = []
    pendingSourcesRef.current = []
    setThreadId(crypto.randomUUID())
    setLockedDatasourceId(null)
    setInput('')
    setMessages([])
    setPendingTimeline([])
    setPendingSources([])
    setInterruptPayload(null)
    setBusy(false)
    syncRunState(createEmptyRun())
  }, [syncRunState])

  const loadSession = useCallback(async (session: AdminSessionSummary) => {
    abortRef.current?.abort()
    setBusy(false)
    setInterruptPayload(null)
    pendingTimelineRef.current = []
    pendingSourcesRef.current = []
    setPendingTimeline([])
    setPendingSources([])
    syncRunState(createEmptyRun())
    setThreadId(session.thread_id)

    try {
      const turns = await fetchThreadTurns(session.thread_id)
      if (turns.length === 0) {
        setLockedDatasourceId(null)
        setMessages([
          {
            id: crypto.randomUUID(),
            role: 'user',
            content: session.first_user_message ?? '(历史会话未保留原始内容)',
          },
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: '这条历史会话来自旧版记录，只保留了侧栏摘要，没有完整的逐轮对话明细。后续新会话会正常保存并可重新打开。',
          },
        ])
        return
      }

      const lockedId = turns[0]?.datasource_id ?? null
      setLockedDatasourceId(lockedId)
      if (lockedId) {
        setSelectedDatasourceId(lockedId)
      }
      setMessages(turns.map((t: ThreadTurnItem) => messageFromThreadTurn(t)))
    } catch {
      setLockedDatasourceId(null)
      setMessages([
        {
          id: crypto.randomUUID(),
          role: 'user',
          content: session.first_user_message ?? '(无法加载)',
        },
      ])
    }
  }, [syncRunState])

  const handleDeleteSession = useCallback(async (session: AdminSessionSummary) => {
    if (!window.confirm(`确定删除这条历史对话？\n\n${session.first_user_message ?? session.thread_id}`)) return
    await deleteAdminSession(session.thread_id)
    if (session.thread_id === threadId) {
      resetThread()
    }
    refreshSessions()
  }, [refreshSessions, resetThread, threadId])

  const appendAssistant = useCallback(
    (text: string, options?: { sqlBlock?: string; turnId?: number }) => {
      const timeline = [...pendingTimelineRef.current]
      const sources = [...pendingSourcesRef.current]
      const run = runAccRef.current
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: text,
          sql: options?.sqlBlock,
          timeline,
          sources,
          memoryTitles: run.recalledMemoryTitles.length > 0 ? [...run.recalledMemoryTitles] : undefined,
          explanation: run.explanation ?? undefined,
          turnId: options?.turnId,
        },
      ])
      pendingTimelineRef.current = []
      pendingSourcesRef.current = []
      setPendingTimeline([])
      setPendingSources([])
      syncRunState(createEmptyRun())
    },
    [syncRunState],
  )

  const sendMessage = useCallback(
    async (resume: boolean) => {
      const text = input.trim()
      if (!text || busy) return

      const activeDatasourceId = effectiveDatasourceId.trim()
      if (!activeDatasourceId) return

      setBusy(true)
      setLockedDatasourceId(activeDatasourceId)
      setInput('')
      pendingTimelineRef.current = []
      pendingSourcesRef.current = []
      setPendingTimeline([])
      setPendingSources([])
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'user', content: text },
      ])

      if (resume) {
        setInterruptPayload(null)
      }
      syncRunState(createEmptyRun())

      abortRef.current?.abort()
      abortRef.current = new AbortController()

      try {
        await streamChat(
          { thread_id: threadId, message: text, datasource_id: activeDatasourceId, resume },
          (event) => {
            const row = summarizeEvent(event)
            if (row) {
              setPendingTimeline((prev) => {
                const next = [...prev, row]
                pendingTimelineRef.current = next
                return next
              })
            }

            if (event.event === 'interrupt') {
              setInterruptPayload(parseInterruptPayload(event.data))
            }

            if (event.event === 'update') {
              const nextSources = sourcesFromUpdateData(event.data)
              if (nextSources.length > 0) {
                setPendingSources((prev) => {
                  const seen = new Set(prev.map((i) => i.id))
                  const merged = [...prev]
                  for (const item of nextSources) {
                    if (!seen.has(item.id)) { seen.add(item.id); merged.push(item) }
                  }
                  const next = merged.slice(0, 12)
                  pendingSourcesRef.current = next
                  return next
                })
              }
              syncRunState(mergeUpdateIntoRun(runAccRef.current, event.data))
            }

            if (event.event === 'step') {
              syncRunState(mergeStepIntoRun(runAccRef.current, event.data))
            }

            if (event.event === 'done') {
              const donePayload =
                event.data && typeof event.data === 'object'
                  ? (
                    event.data as {
                      ok?: boolean
                      error?: unknown
                      assistant_turn_id?: unknown
                      response_text?: unknown
                    }
                  )
                  : null

              if (donePayload?.ok === false) {
                appendAssistant(
                  `运行失败：${typeof donePayload.error === 'string' ? donePayload.error : '未知错误'}`,
                )
                return
              }

              const nextRun = runAccRef.current
              appendAssistant(
                typeof donePayload?.response_text === 'string'
                  ? donePayload.response_text
                  : buildAssistantSummary(nextRun),
                {
                  sqlBlock: nextRun.sql ?? undefined,
                  turnId:
                    typeof donePayload?.assistant_turn_id === 'number'
                      ? donePayload.assistant_turn_id
                      : undefined,
                },
              )

              refreshSessions()
            }
          },
          abortRef.current.signal,
        )
      } catch (error) {
        appendAssistant(`请求失败：${error instanceof Error ? error.message : String(error)}`)
      } finally {
        setBusy(false)
      }
    },
    [appendAssistant, busy, effectiveDatasourceId, input, refreshSessions, syncRunState, threadId],
  )

  const handleFeedback = useCallback(
    (messageId: string, rating: 'positive' | 'negative') => {
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, feedbackRating: rating } : m)),
      )
      const msg = messages.find((m) => m.id === messageId)
      if (!msg || !msg.turnId) return
      void submitTurnFeedback(threadId, msg.turnId, { rating }).catch(() => {})
    },
    [messages, threadId],
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        void sendMessage(Boolean(interruptPayload?.prompt))
      }
    },
    [interruptPayload, sendMessage],
  )

  const isInterrupt = Boolean(interruptPayload?.prompt)
  const liveAssistantMessage: ChatMessage | null = busy
    ? {
      id: '__live_assistant__',
      role: 'assistant',
      content:
        liveRun.responseText ??
        '正在分析你的问题。\n\n下面会实时展示 Agent 的决策摘要、工具调用、记忆命中、证据检索与 SQL 产出。',
      sql: liveRun.sql ?? undefined,
      timeline: pendingTimeline.length > 0 ? pendingTimeline : undefined,
      sources: pendingSources.length > 0 ? pendingSources : undefined,
      memoryTitles:
        liveRun.recalledMemoryTitles.length > 0 ? liveRun.recalledMemoryTitles : undefined,
      explanation: liveRun.explanation ?? undefined,
      streaming: true,
    }
    : null

  return (
    <div className="flex h-full bg-[linear-gradient(180deg,#fbfaf7_0%,var(--background)_100%)]">
      {/* ─── Sidebar ─── */}
      <div
        className={cn(
          'flex flex-col border-r border-[color-mix(in_srgb,var(--line)_72%,transparent)] bg-white/68 backdrop-blur-2xl transition-[width] duration-200',
          sidebarOpen ? 'w-[248px]' : 'w-0 overflow-hidden border-r-0',
        )}
      >
        <div className="flex h-12 items-center gap-2 border-b border-[var(--line)] px-3">
          <button
            type="button"
            onClick={resetThread}
            className="flex flex-1 items-center gap-2 rounded-xl px-2.5 py-1.5 text-[12px] font-medium text-[var(--foreground)] transition-colors hover:bg-white/70"
          >
            <PencilSimple className="size-3.5" />
            新对话
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2.5 py-3">
          {sessionsLoading && sessions.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-[11px] text-[var(--muted-foreground)]">
              <CircleNotch className="mr-1.5 size-3 animate-spin" />
              加载中
            </div>
          ) : sessions.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[var(--line)] bg-white/42 px-3 py-8 text-center text-[11px] text-[var(--muted-foreground)]">
              暂无历史对话
            </div>
          ) : (
            <div className="space-y-1.5">
              {sessions.map((s) => (
                <div
                  key={s.thread_id}
                  className={cn(
                    'group flex items-start gap-1 rounded-2xl border px-1.5 py-1.5 transition-all',
                    s.thread_id === threadId
                      ? 'border-[color-mix(in_srgb,var(--primary)_22%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_8%,white)] shadow-[inset_0_1px_0_rgba(255,255,255,0.56)]'
                      : 'border-transparent hover:border-[var(--line)] hover:bg-white/62',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => void loadSession(s)}
                    className="flex min-w-0 flex-1 flex-col gap-1 rounded-xl px-1.5 py-1 text-left"
                  >
                    <span className="line-clamp-1 text-[12px] leading-5 text-[var(--foreground)]">
                      {s.first_user_message || s.thread_id.slice(0, 8)}
                    </span>
                    <span className="flex items-center gap-1.5 text-[10px] text-[var(--muted-foreground)]">
                      <Clock className="size-2.5" />
                      {relativeTime(s.last_activity_at)}
                      {s.turn_count > 0 ? (
                        <>
                          <ChatText className="ml-1 size-2.5" />
                          {s.turn_count}
                        </>
                      ) : null}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDeleteSession(s)}
                    className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md text-[var(--muted-foreground)] opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                    title="删除历史对话"
                    aria-label="删除历史对话"
                  >
                    <Trash className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ─── Main chat area ─── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar (minimal) */}
        <div className="flex h-12 items-center gap-2 border-b border-[var(--line)] bg-white/48 px-3 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="flex size-8 items-center justify-center rounded-xl text-[var(--foreground-soft)] transition-colors hover:bg-white/72 hover:text-[var(--foreground)]"
            aria-label="切换侧栏"
          >
            <SidebarSimple className="size-4" />
          </button>

          <div className="flex-1" />

          <ProductSelect
            value={selectedDatasourceId || effectiveDatasourceId}
            options={datasourceSelectOptions}
            onChange={handleDatasourceChange}
            placeholder={datasourceLoading ? '加载数据源…' : '选择数据源'}
            disabled={datasourceLocked || busy || datasourceLoading || datasourceSelectOptions.length === 0}
            title={
              datasourceLocked
                ? '当前对话已绑定数据源；点击右上角「新对话」后可切换'
                : busy
                  ? 'Agent 执行中，请稍后再切换数据源'
                  : undefined
            }
            className="w-[min(240px,42vw)] [&_button]:h-8 [&_button]:rounded-lg [&_button]:text-[12px]"
          />

          <button
            type="button"
            onClick={resetThread}
            className="flex size-8 items-center justify-center rounded-xl text-[var(--foreground-soft)] transition-colors hover:bg-white/72 hover:text-[var(--foreground)]"
            aria-label="新对话"
          >
            <ArrowsClockwise className="size-4" />
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[780px] px-4 py-6">
            {messages.length === 0 ? (
              <EmptyState
                suggestions={suggestions}
                suggestionsLoading={suggestionsLoading}
                onSelect={setInput}
              />
            ) : (
              <div className="space-y-5">
                {messages.map((msg) => (
                  <MessageBubble
                    key={msg.id}
                    message={msg}
                    datasourceId={effectiveDatasourceId}
                    threadId={threadId}
                    onFeedback={handleFeedback}
                  />
                ))}
                {liveAssistantMessage ? (
                  <MessageBubble
                    key={liveAssistantMessage.id}
                    message={liveAssistantMessage}
                    datasourceId={effectiveDatasourceId}
                    threadId={threadId}
                    onFeedback={handleFeedback}
                  />
                ) : null}
              </div>
            )}
          </div>
        </div>

        {/* Clarification banner */}
        {isInterrupt && !busy ? (
          <div className="border-t border-[var(--line)] bg-[color-mix(in_srgb,var(--primary)_6%,white)]">
            <div className="mx-auto max-w-3xl px-4 py-3">
              <p className="text-[13px] leading-6 text-[var(--foreground)]">
                <span className="font-medium">需要补充信息：</span>
                {interruptPayload?.prompt}
              </p>
            </div>
          </div>
        ) : null}

        {/* Input area */}
        <div className="border-t border-[var(--line)] bg-white/58 backdrop-blur-xl">
          <div className="mx-auto max-w-[780px] px-4 py-3">
            <div className="relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isInterrupt ? '输入补充信息...' : '输入你的问题...'}
                disabled={busy}
                rows={1}
                className="w-full resize-none rounded-2xl border border-[var(--line)] bg-white/82 px-4 py-3 pr-14 text-[14px] leading-6 text-[var(--foreground)] shadow-[0_10px_28px_rgba(17,24,39,0.05),inset_0_1px_0_rgba(255,255,255,0.62)] outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-[var(--muted-foreground)] focus:border-[color-mix(in_srgb,var(--primary)_38%,var(--line))] focus:shadow-[0_12px_32px_rgba(17,24,39,0.07),inset_0_1px_0_rgba(255,255,255,0.62),0_0_0_2px_color-mix(in_srgb,var(--primary)_14%,transparent)] disabled:opacity-50"
                style={{ minHeight: '48px', maxHeight: '160px', fieldSizing: 'content' } as React.CSSProperties}
              />
              <button
                type="button"
                disabled={busy || !input.trim()}
                onClick={() => void sendMessage(isInterrupt)}
                className="absolute bottom-2.5 right-2.5 flex size-9 items-center justify-center rounded-xl bg-[var(--primary)] text-white shadow-[0_10px_24px_rgba(36,88,211,0.22)] transition-all hover:brightness-110 disabled:opacity-40 disabled:shadow-none"
              >
                <PaperPlaneTilt className="size-4" weight="fill" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── Empty state ─── */

function EmptyState({
  suggestions,
  suggestionsLoading,
  onSelect,
}: {
  suggestions: string[]
  suggestionsLoading: boolean
  onSelect: (v: string) => void
}) {
  return (
    <FadeContent duration={500}>
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-7 text-center">
        <div className="space-y-2 rounded-[1.8rem] border border-[var(--line)] bg-white/54 px-8 py-7 shadow-[0_18px_50px_rgba(17,24,39,0.06),inset_0_1px_0_rgba(255,255,255,0.64)] backdrop-blur-xl">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--primary)_10%,white)]">
            <Sparkle className="size-6 text-[var(--primary)]" weight="duotone" />
          </div>
          <p className="text-sm font-semibold text-[var(--foreground)]">开始一次数据对话</p>
          <p className="text-[13px] text-[var(--foreground-soft)]">
            用自然语言描述你的查询需求
          </p>
        </div>

        {suggestionsLoading ? (
          <div className="flex items-center gap-2 text-[12px] text-[var(--muted-foreground)]">
            <CircleNotch className="size-3.5 animate-spin" />
            正在为你生成推荐问题...
          </div>
        ) : suggestions.length > 0 ? (
          <div className="flex max-w-xl flex-wrap justify-center gap-2">
            {suggestions.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => onSelect(prompt)}
                className="rounded-full border border-[var(--line)] bg-white/70 px-4 py-2 text-[13px] text-[var(--foreground-soft)] shadow-[inset_0_1px_0_rgba(255,255,255,0.58)] transition-all hover:border-[color-mix(in_srgb,var(--primary)_28%,var(--line))] hover:bg-white/90 hover:text-[var(--foreground)]"
              >
                {prompt}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </FadeContent>
  )
}

/* ─── Message bubble ─── */

function MessageBubble({
  message,
  datasourceId,
  threadId,
  onFeedback,
}: {
  message: ChatMessage
  datasourceId: string
  threadId: string
  onFeedback?: (messageId: string, rating: 'positive' | 'negative') => void
}) {
  if (message.role === 'user') {
    return (
      <FadeContent duration={300}>
        <div className="flex justify-end">
          <div className="max-w-[80%] rounded-2xl rounded-br-md bg-[var(--primary)] px-4 py-3 text-[14px] leading-7 text-white shadow-[0_4px_14px_rgba(36,88,211,0.2)]">
            {message.content}
          </div>
        </div>
      </FadeContent>
    )
  }

  return (
    <FadeContent duration={400}>
      <div className="space-y-3">
        <div className="space-y-2">
          {message.streaming ? (
            <div className="flex items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
              <CircleNotch className="size-3.5 animate-spin" />
              Agent 正在运行
            </div>
          ) : null}
          <MessageResponse
            className={cn(
              'text-[14px] leading-7 text-[var(--foreground)]',
              '[&_code]:rounded [&_code]:bg-[color-mix(in_srgb,var(--surface)_88%,white)] [&_code]:px-1.5 [&_code]:py-0.5',
              '[&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-[var(--line)]',
              '[&_pre]:bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] [&_pre]:p-4',
              '[&_p]:my-0 [&_p+_p]:mt-4 [&_ul]:my-3 [&_ol]:my-3 [&_li]:my-1',
            )}
          >
            {message.content}
          </MessageResponse>
        </div>

        {message.sql || (message.timeline && message.timeline.length > 0) ? (
          <AssistantAccordion
            message={message}
            datasourceId={datasourceId}
            threadId={threadId}
          />
        ) : null}

        {!message.streaming ? (
          <FeedbackBar
            message={message}
            onFeedback={onFeedback}
          />
        ) : null}
      </div>
    </FadeContent>
  )
}

/* ─── Inline accordion (SQL + timeline + execution) ─── */

function AssistantAccordion({
  message,
  datasourceId,
  threadId,
}: {
  message: ChatMessage
  datasourceId: string
  threadId: string
}) {
  const [open, setOpen] = useState(Boolean(message.streaming || message.sql))
  const [execResult, setExecResult] = useState<ExecuteResponse | null>(null)
  const [execError, setExecError] = useState<string | null>(null)
  const [executing, setExecuting] = useState(false)

  const handleExecute = useCallback(async () => {
    if (!message.sql) return
    setExecuting(true)
    setExecError(null)
    setExecResult(null)
    try {
      const result = await runSql({ datasource_id: datasourceId, thread_id: threadId, sql: message.sql })
      setExecResult(result)
    } catch (e) {
      setExecError(e instanceof Error ? e.message : String(e))
    } finally {
      setExecuting(false)
    }
  }, [datasourceId, message.sql, threadId])

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-[12px] font-medium text-[var(--foreground-soft)] transition-colors hover:text-[var(--foreground)]"
      >
        {open ? <CaretDown className="size-3.5" /> : <CaretRight className="size-3.5" />}
        <span>推理过程与 SQL</span>
        {message.memoryTitles && message.memoryTitles.length > 0 ? (
          <Badge variant="outline" className="ml-auto text-[9px]">
            {memoryBadgeLabel(message.memoryTitles.length)}
          </Badge>
        ) : null}
        {message.sources && message.sources.length > 0 ? (
          <Badge variant="outline" className="text-[9px]">
            {evidenceBadgeLabel(message.sources.length)}
          </Badge>
        ) : null}
      </button>

      {open ? (
        <div className="space-y-3 border-t border-[var(--line)] px-4 py-3">
          {message.sources && message.sources.length > 0 ? (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {message.sources.map((s) => (
                <div
                  key={s.id}
                  className="min-w-[180px] max-w-[240px] shrink-0 rounded-lg border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_88%,white)] px-3 py-2"
                >
                  <Badge variant="outline" className="mb-2 text-[9px]">
                    {sourceCategoryLabel(s.title)}
                  </Badge>
                  <div className="text-[11px] font-medium text-[var(--foreground)]">{s.title}</div>
                  <div className="mt-1 line-clamp-3 text-[10px] leading-5 text-[var(--foreground-soft)]">{s.preview}</div>
                </div>
              ))}
            </div>
          ) : null}

          {message.memoryTitles && message.memoryTitles.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {message.memoryTitles.map((t) => (
                <Badge key={t} variant="outline" className="text-[9px]">
                  <Sparkle className="mr-1 size-3" />
                  {t}
                </Badge>
              ))}
            </div>
          ) : null}

          {message.explanation ? (
            <p className="text-[12px] leading-6 text-[var(--foreground-soft)]">{message.explanation}</p>
          ) : null}

          {message.sql ? (
            <div className="space-y-2">
              <SqlBlock sql={message.sql} />
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void handleExecute()}
                  disabled={executing || message.streaming}
                  className="h-8 gap-1.5 rounded-lg px-3 text-xs"
                >
                  {executing ? (
                    <CircleNotch className="size-3.5 animate-spin" />
                  ) : (
                    <Play className="size-3.5" weight="fill" />
                  )}
                  {message.streaming ? '等待本轮完成' : '执行查询'}
                </Button>
              </div>
            </div>
          ) : null}

          {execError ? (
            <div className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_18%,var(--line))] bg-[color-mix(in_srgb,var(--danger-surface)_94%,white)] px-3 py-2 text-[12px] text-[var(--danger)]">
              {execError}
            </div>
          ) : null}

          {execResult ? (
            <div className="space-y-2">
              <div className="text-[11px] text-[var(--muted-foreground)]">
                {execResult.rowcount} 条记录
                {execResult.truncated ? '（已达到返回上限）' : ''}
              </div>
              <ResultTable rows={execResult.rows} />
            </div>
          ) : null}

          {message.timeline && message.timeline.length > 0 ? (
            <InlineTimeline rows={message.timeline} defaultOpen={Boolean(message.streaming)} />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

/* ─── Feedback bar ─── */

function FeedbackBar({
  message,
  onFeedback,
}: {
  message: ChatMessage
  onFeedback?: (messageId: string, rating: 'positive' | 'negative') => void
}) {
  const [localRating, setLocalRating] = useState<'positive' | 'negative' | null>(
    message.feedbackRating ?? null,
  )

  const handleRate = useCallback(
    (rating: 'positive' | 'negative') => {
      if (localRating === rating) return
      setLocalRating(rating)
      onFeedback?.(message.id, rating)
    },
    [localRating, message.id, onFeedback],
  )

  if (message.streaming || !message.turnId) {
    return null
  }

  return (
    <div className="flex items-center gap-1 pt-1">
      <button
        type="button"
        onClick={() => handleRate('positive')}
        className={cn(
          'flex size-7 items-center justify-center rounded-md transition-all',
          localRating === 'positive'
            ? 'bg-[color-mix(in_srgb,var(--primary)_12%,white)] text-[var(--primary)]'
            : 'text-[var(--muted-foreground)] hover:bg-[color-mix(in_srgb,var(--surface)_80%,white)] hover:text-[var(--foreground)]',
        )}
        title="有帮助"
      >
        <ThumbsUp className="size-3.5" weight={localRating === 'positive' ? 'fill' : 'regular'} />
      </button>
      <button
        type="button"
        onClick={() => handleRate('negative')}
        className={cn(
          'flex size-7 items-center justify-center rounded-md transition-all',
          localRating === 'negative'
            ? 'bg-[color-mix(in_srgb,var(--danger)_12%,white)] text-[var(--danger)]'
            : 'text-[var(--muted-foreground)] hover:bg-[color-mix(in_srgb,var(--surface)_80%,white)] hover:text-[var(--foreground)]',
        )}
        title="需改进"
      >
        <ThumbsDown className="size-3.5" weight={localRating === 'negative' ? 'fill' : 'regular'} />
      </button>
    </div>
  )
}

/* ─── Timeline accordion ─── */

function LearningOutcomeCard({ row }: { row: TimelineRow }) {
  const payload = row.payload
  if (!payload || row.stepId !== 'memory_autoupdate' || payload.phase !== 'complete') {
    return null
  }

  const memoryCount = typeof payload.memory_count === 'number' ? payload.memory_count : 0
  const qaExampleCount = typeof payload.qa_example_count === 'number' ? payload.qa_example_count : 0
  const signalBuffered = payload.signal_buffered === true
  const updates = Array.isArray(payload.updates)
    ? payload.updates.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    : []

  const metricClass = 'rounded-xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_88%,white)] px-3 py-2'

  return (
    <div className="mt-1.5 space-y-2 rounded-xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_82%,white)] px-3 py-3">
      <div className="grid gap-2 sm:grid-cols-3">
        <div className={metricClass}>
          <div className="text-[10px] text-[var(--muted-foreground)]">主记忆</div>
          <div className="mt-1 text-sm font-semibold text-[var(--foreground)]">{memoryCount}</div>
        </div>
        <div className={metricClass}>
          <div className="text-[10px] text-[var(--muted-foreground)]">QA 案例</div>
          <div className="mt-1 text-sm font-semibold text-[var(--foreground)]">{qaExampleCount}</div>
        </div>
        <div className={metricClass}>
          <div className="text-[10px] text-[var(--muted-foreground)]">新领域缓冲</div>
          <div className="mt-1 text-sm font-semibold text-[var(--foreground)]">{signalBuffered ? '是' : '否'}</div>
        </div>
      </div>

      {updates.length > 0 ? (
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-[var(--muted-foreground)]">主记忆更新</div>
          {updates.slice(0, 4).map((item, index) => {
            const title = typeof item.title === 'string' ? item.title : `条目 ${index + 1}`
            const action = item.action === 'replaced' ? '改写' : '新增'
            const content = typeof item.content === 'string' ? item.content : ''
            return (
              <div
                key={`${title}-${index}`}
                className="rounded-lg border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_92%,white)] px-2.5 py-2 text-[10px] leading-5 text-[var(--muted-foreground)]"
              >
                <div className="font-medium text-[var(--foreground)]">{action} · {title}</div>
                {content ? <div className="mt-0.5">{content}</div> : null}
              </div>
            )
          })}
        </div>
      ) : null}

      {typeof payload.summary === 'string' && payload.summary ? (
        <div className="text-[10px] leading-5 text-[var(--muted-foreground)]">{payload.summary}</div>
      ) : null}
    </div>
  )
}

function InlineTimeline({ rows, defaultOpen }: { rows: TimelineRow[]; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
      >
        {open ? <CaretDown className="size-3" /> : <CaretRight className="size-3" />}
        {rows.length} 个推理步骤
      </button>
      {open ? (
        <div className="mt-2 space-y-1 border-l-2 border-[var(--line)] pl-3">
          {rows.map((row) => (
            <div key={row.id} className="py-1">
              <div className="text-[11px] font-medium text-[var(--foreground)]">{row.label}</div>
              {row.stepId === 'memory_autoupdate' ? (
                <LearningOutcomeCard row={row} />
              ) : row.detail ? (
                <div className="mt-0.5 whitespace-pre-wrap break-words rounded-lg bg-[color-mix(in_srgb,var(--surface)_88%,white)] px-2.5 py-2 font-mono text-[10px] leading-5 text-[var(--muted-foreground)]">
                  {row.detail}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
