/**
 * Helpers for SSE payloads from `/api/v1/chat/stream` (LangGraph custom steps + state updates).
 */

export type InterruptPayload = {
  interruptId?: string
  kind?: string
  prompt?: string
  ambiguityReason?: string
}

export type SourceItem = {
  id: string
  title: string
  preview: string
}

export type StepPayload = {
  step_id?: string
  name?: string
  phase?: string
  payload?: unknown
  sql?: string
  error?: string
  text?: string
  content?: string
  tool?: string
  step?: number
  intent?: string
  args_preview?: string
  summary?: string
  result_preview?: string
  memory_titles?: string[]
  summary_status?: string
  recent_turn_count?: number
  stored_turn_count?: number
  compression_count?: number
  compression_applied?: boolean
  tool_calls?: string[]
  steps_used?: number
  has_sql?: boolean
  remaining?: number
  recalled_memory_titles?: string[]
  thread_summary_status?: string
  updates?: Array<Record<string, unknown>>
  [key: string]: unknown
}

/** Parse interrupt envelope `{ interrupt_id, value: { kind, prompt, ambiguity_reason } }` */
export function parseInterruptPayload(data: unknown): InterruptPayload | null {
  if (!data || typeof data !== 'object') return null
  const d = data as Record<string, unknown>
  const interruptId =
    typeof d.interrupt_id === 'string'
      ? d.interrupt_id
      : typeof d.interruptId === 'string'
        ? d.interruptId
        : undefined
  const value = d.value
  if (!value || typeof value !== 'object') {
    return interruptId ? { interruptId } : null
  }
  const v = value as Record<string, unknown>
  return {
    interruptId,
    kind: typeof v.kind === 'string' ? v.kind : undefined,
    prompt: typeof v.prompt === 'string' ? v.prompt : undefined,
    ambiguityReason:
      typeof v.ambiguity_reason === 'string'
        ? v.ambiguity_reason
        : typeof v.ambiguityReason === 'string'
          ? v.ambiguityReason
          : undefined,
  }
}

function walkForRagChunks(obj: unknown, depth = 0): unknown[] {
  if (depth > 8 || !obj || typeof obj !== 'object') return []
  const o = obj as Record<string, unknown>
  if (Array.isArray(o.rag_chunks)) return o.rag_chunks
  for (const v of Object.values(o)) {
    const found = walkForRagChunks(v, depth + 1)
    if (found.length) return found
  }
  return []
}

/** Build citation cards from workflow state updates that include `rag_chunks`. */
export function sourcesFromUpdateData(data: unknown): SourceItem[] {
  const chunks = walkForRagChunks(data)
  const out: SourceItem[] = []
  for (const c of chunks) {
    if (!c || typeof c !== 'object') continue
    const row = c as Record<string, unknown>
    const id = String(row.id ?? `chunk-${out.length}`)
    const content = typeof row.content === 'string' ? row.content : ''
    const meta =
      row.metadata && typeof row.metadata === 'object'
        ? (row.metadata as Record<string, unknown>)
        : {}
    const title =
      (typeof meta.title === 'string' && meta.title) ||
      (typeof meta.source === 'string' && meta.source) ||
      `知识片段 ${id}`
    const preview = content.trim().replace(/\s+/g, ' ').slice(0, 220)
    out.push({ id, title, preview })
  }
  return out.slice(0, 8)
}

function truncateText(value: string, limit = 360): string {
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}

function joinBits(bits: Array<string | undefined | null | false>): string | undefined {
  const filtered = bits.filter((item): item is string => Boolean(item && item.trim()))
  return filtered.length > 0 ? filtered.join('\n') : undefined
}

/** Human-readable line for timeline detail from a custom `step` chunk. */
export function formatStepDetail(d: StepPayload): string | undefined {
  if (d.step_id === 'reasoning_note' && typeof d.text === 'string') {
    return truncateText(d.text, 1200)
  }
  if (d.step_id === 'tool_call') {
    return joinBits([
      typeof d.intent === 'string' ? d.intent : undefined,
      typeof d.args_preview === 'string' ? `参数: ${d.args_preview}` : undefined,
      typeof d.summary === 'string' ? d.summary : undefined,
      typeof d.result_preview === 'string' ? `结果: ${d.result_preview}` : undefined,
    ])
  }
  if (
    d.step_id === 'load_datasource_memory' &&
    d.phase === 'complete' &&
    Array.isArray(d.memory_titles)
  ) {
    return d.memory_titles.length > 0
      ? `命中记忆: ${d.memory_titles.join('、')}`
      : '未命中相关记忆'
  }
  if (d.step_id === 'load_thread_summary' && d.phase === 'complete') {
    return joinBits([
      typeof d.summary_status === 'string' ? `摘要状态: ${d.summary_status}` : undefined,
      typeof d.recent_turn_count === 'number' ? `近期轮次: ${d.recent_turn_count}` : undefined,
      typeof d.stored_turn_count === 'number' ? `累计轮次: ${d.stored_turn_count}` : undefined,
      typeof d.compression_count === 'number' && d.compression_count > 0
        ? `压缩次数: ${d.compression_count}`
        : undefined,
      typeof d.compression_applied === 'boolean'
        ? (d.compression_applied ? '已执行上下文压缩' : '未执行上下文压缩')
        : undefined,
    ])
  }
  if (d.step_id === 'memory_autoupdate' && d.phase === 'complete') {
    const updates = Array.isArray(d.updates)
      ? d.updates.filter(
        (item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'),
      )
      : []
    if (updates.length === 0) {
      return typeof d.summary === 'string' ? d.summary : '本轮未沉淀新的稳定主记忆'
    }
    return updates.slice(0, 4).map((item) => {
      const title = typeof item.title === 'string' ? item.title : '未命名条目'
      const action = item.action === 'replaced' ? '改写' : '新增'
      const section = typeof item.section === 'string' ? item.section : ''
      const content = typeof item.content === 'string' ? truncateText(item.content, 72) : ''
      return `${action} ${title}${section ? ` · ${section}` : ''}${content ? `：${content}` : ''}`
    }).join('\n')
  }
  if (d.step_id === 'agent_loop' && d.phase === 'complete') {
    return joinBits([
      typeof d.step === 'number' ? `当前迭代: ${d.step}` : undefined,
      typeof d.steps_used === 'number' ? `总共迭代 ${d.steps_used} 步` : undefined,
      Array.isArray(d.tool_calls) && d.tool_calls.length > 0
        ? `调用工具: ${d.tool_calls.join(' -> ')}`
        : undefined,
      typeof d.has_sql === 'boolean' ? (d.has_sql ? '已生成 SQL' : '未生成 SQL') : undefined,
    ])
  }
  if (d.step_id === 'autonomous_agent' && d.phase === 'complete') {
    return joinBits([
      typeof d.steps_used === 'number' ? `执行了 ${d.steps_used} 步` : undefined,
      Array.isArray(d.tool_calls) && d.tool_calls.length > 0
        ? `工具数: ${d.tool_calls.length}`
        : undefined,
      typeof d.has_sql === 'boolean' ? (d.has_sql ? '已产出 SQL' : '未产出 SQL') : undefined,
    ])
  }
  if (d.step_id === 'budget_warning' && typeof d.remaining === 'number') {
    return `剩余 ${d.remaining} 步预算`
  }
  if (d.phase === 'complete' && typeof d.sql === 'string') {
    return truncateText(d.sql, 420)
  }
  if (d.phase === 'error' && typeof d.error === 'string') return d.error
  if (d.payload !== undefined) {
    const s = JSON.stringify(d.payload)
    return s.length > 280 ? `${s.slice(0, 280)}…` : s
  }
  return undefined
}

export type RunAccumulator = {
  sql: string | null
  explanation: string | null
  sqlError: string | null
  responseText: string | null
  recalledMemoryTitles: string[]
  threadSummaryStatus: string | null
  recentTurnCount: number
}

export function mergeStepIntoRun(
  acc: RunAccumulator,
  raw: unknown,
): RunAccumulator {
  if (!raw || typeof raw !== 'object') return acc
  const d = raw as StepPayload
  const sid = typeof d.step_id === 'string' ? d.step_id : ''
  if (
    sid === 'assistant_message' &&
    typeof d.content === 'string' &&
    d.phase === 'complete'
  ) {
    return { ...acc, responseText: d.content }
  }
  if (
    sid === 'generate_sql' &&
    typeof d.sql === 'string' &&
    d.phase === 'complete'
  ) {
    return { ...acc, sql: d.sql }
  }
  if (sid === 'generate_sql' && typeof d.error === 'string' && d.phase === 'error') {
    return { ...acc, sqlError: d.error }
  }
  if (
    sid === 'load_datasource_memory' &&
    Array.isArray(d.memory_titles) &&
    d.phase === 'complete'
  ) {
    return {
      ...acc,
      recalledMemoryTitles: d.memory_titles.filter(
        (item): item is string => typeof item === 'string',
      ),
    }
  }
  if (
    sid === 'load_thread_summary' &&
    typeof d.summary_status === 'string' &&
    d.phase === 'complete'
  ) {
    return {
      ...acc,
      threadSummaryStatus: d.summary_status,
      recentTurnCount:
        typeof d.recent_turn_count === 'number' ? d.recent_turn_count : acc.recentTurnCount,
    }
  }
  if (sid === 'complete' && typeof d.thread_summary_status === 'string') {
    return {
      ...acc,
      threadSummaryStatus: d.thread_summary_status,
      recalledMemoryTitles: Array.isArray(d.recalled_memory_titles)
        ? d.recalled_memory_titles.filter((item): item is string => typeof item === 'string')
        : acc.recalledMemoryTitles,
    }
  }
  return acc
}

/** LangGraph `updates` chunks are `{ node_name: partial_state }`. */
export function mergeUpdateIntoRun(
  acc: RunAccumulator,
  data: unknown,
): RunAccumulator {
  if (!data || typeof data !== 'object') return acc
  const root = data as Record<string, unknown>
  for (const v of Object.values(root)) {
    if (!v || typeof v !== 'object') continue
    const u = v as Record<string, unknown>
    if (typeof u.generated_sql === 'string') {
      acc = { ...acc, sql: u.generated_sql }
    }
    if (typeof u.sql_explanation === 'string') {
      acc = { ...acc, explanation: u.sql_explanation }
    }
    if (typeof u.sql_error === 'string') {
      acc = { ...acc, sqlError: u.sql_error }
    }
    if (typeof u.response_text === 'string') {
      acc = { ...acc, responseText: u.response_text }
    }
    if (Array.isArray(u.recalled_memory_titles)) {
      acc = {
        ...acc,
        recalledMemoryTitles: u.recalled_memory_titles.filter(
          (item): item is string => typeof item === 'string',
        ),
      }
    }
    if (typeof u.thread_summary_status === 'string') {
      acc = { ...acc, threadSummaryStatus: u.thread_summary_status }
    }
    if (typeof u.recent_turn_count === 'number') {
      acc = { ...acc, recentTurnCount: u.recent_turn_count }
    }
  }
  return acc
}

export function buildAssistantSummary(acc: RunAccumulator): string {
  if (acc.responseText) {
    return acc.responseText
  }
  if (acc.sqlError) {
    return `SQL 生成已中止：${acc.sqlError}`
  }
  if (acc.sql) {
    const bits: string[] = []
    if (acc.recalledMemoryTitles.length) {
      bits.push(`召回记忆：${acc.recalledMemoryTitles.join('、')}。`)
    }
    bits.push('已生成 SQL，并同步到下方检查区。')
    if (acc.explanation) {
      bits.push(acc.explanation)
    }
    return bits.join(' ')
  }
  return '本次运行已结束，详细过程可在推理面板中查看。'
}
