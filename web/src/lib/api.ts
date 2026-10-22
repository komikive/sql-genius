/** Typed clients for FastAPI routes under `/api/v1`. Dev proxy: `vite.config.ts`. */

export type ChatStreamRequest = {
  thread_id: string
  message: string
  datasource_id?: string
  resume?: boolean
}

export type SseEventName = 'step' | 'interrupt' | 'update' | 'done' | 'message'

export type ChatStreamEvent = {
  event: SseEventName
  data: unknown
}

export type ExecuteRequest = {
  datasource_id: string
  sql: string
  thread_id?: string | null
}

export type ExecuteResponse = {
  rows: Record<string, unknown>[]
  rowcount: number
  truncated: boolean
}

export type Dialect = 'mysql' | 'postgresql'

export type DatasourceOption = {
  id: string
  label: string
  dialect: string | null
  is_default: boolean
}

type DatasourceListResponse = {
  items: DatasourceOption[]
}

export type AdminDatasourceSummary = {
  id: string
  display_name: string
  dialect: Dialect
  is_default: boolean
  connection_url_masked: string
  last_introspected_at: string | null
}

export type AdminDatasourceDetail = AdminDatasourceSummary & {
  has_connection_url: boolean
  schema_available: boolean
}

type AdminDatasourceListResponse = {
  items: AdminDatasourceSummary[]
}

export type AdminDatasourceCreateRequest = {
  id: string
  display_name: string
  dialect: Dialect
  connection_url: string
  is_default?: boolean
}

export type AdminDatasourceUpdateRequest = Partial<
  Omit<AdminDatasourceCreateRequest, 'id'>
>

export type AdminDatasourceTestRequest = {
  id?: string
  connection_url?: string
  dialect?: Dialect
}

export type AdminDatasourceTestResponse = {
  ok: boolean
  message: string
}

export type AdminDatasourceIntrospectResponse = {
  ok: boolean
  message: string
  captured_at: string
  table_count: number
  column_count: number
  truncated: boolean
}

export type AdminSkillPackSummary = {
  id: string
  datasource_id: string | null
  name: string
  slug: string
  status: string
  origin: string
  activation_mode: string
  confidence: number
  summary: string
  keywords: string[]
  table_focus: string[]
  created_at: string
  updated_at: string
}

type AdminSkillPackListResponse = {
  items: AdminSkillPackSummary[]
}

export type AdminDatasourceProfile = {
  datasource_id: string
  analysis_status: string
  summary: string
  analysis_error: string | null
  last_analyzed_at: string | null
  profile_json: Record<string, unknown> | null
  active_memory_count: number
  thread_summary_count: number
  draft_skill_count: number
  skill_packs: AdminSkillPackSummary[]
}

export type AdminOnboardingRunEvent = {
  timestamp: string
  phase: string
  message: string
  level: string
  payload?: Record<string, unknown> | null
}

export type AdminOnboardingRun = {
  id: string
  datasource_id: string
  status: string
  phase: string
  status_message: string
  error: string | null
  started_at: string | null
  completed_at: string | null
  events: AdminOnboardingRunEvent[]
  result_payload: Record<string, unknown> | null
}

export type AdminAnalysisWorkspaceHistoryItem = {
  run_id: string
  status: string
  started_at: string | null
  completed_at: string | null
  phase: string
  headline: string
  clarification_pending: boolean
  preview_available: boolean
}

export type AdminAnalysisWorkspaceClarification = {
  prompt: string
  reason: string
  input_kind: string
  options: string[]
}

export type AdminAnalysisWorkspace = {
  datasource: AdminDatasourceDetail
  active_run: AdminOnboardingRun | null
  status: string
  timeline_items: AdminOnboardingRunEvent[]
  clarification: AdminAnalysisWorkspaceClarification | null
  conversation: Array<Record<string, unknown>>
  result_preview: Record<string, unknown> | null
  history: AdminAnalysisWorkspaceHistoryItem[]
  debug_available: boolean
  selected_run_id: string | null
}

export type AdminOnboardingContextQuestion = {
  question: string
  answer: string
}

export type AdminOnboardingContext = {
  datasource_id: string
  notes: string
  questions: AdminOnboardingContextQuestion[]
  conversation: Array<Record<string, unknown>>
}

export type OnboardingChatQuestion = {
  prompt: string
  reason: string
  input_kind: string
  options: string[]
}

export type OnboardingChatEvent =
  | { event: 'step'; data: Record<string, unknown> }
  | { event: 'message'; data: { role: string; content: string } }
  | { event: 'question'; data: OnboardingChatQuestion }
  | { event: 'done'; data: { ok: boolean; should_rerun_analysis?: boolean } }

export type AdminDatasourceMemoryEvidence = {
  kind: string
  title: string
  excerpt: string
  updated_at: string | null
}

export type AdminDatasourceMemoryUpdateTrace = {
  title: string
  content: string
  memory_type: string
  section: string
  action: string
  source: string
  change_summary: string | null
  confidence: number
  source_excerpt: string | null
  thread_id: string | null
  updated_at: string | null
}

export type AdminDatasourceMemoryDocument = {
  datasource_id: string
  title: string
  markdown_content: string
  source_overview: string | null
  structured_outline: Array<Record<string, unknown>>
  document_metadata: Record<string, unknown> | null
  management_mode: string
  item_count: number
  recent_updates: AdminDatasourceMemoryUpdateTrace[]
  evidence_items: AdminDatasourceMemoryEvidence[]
  created_at: string
  updated_at: string
}

export type AdminDatasourceMemoryDocumentUpdateRequest = Partial<
  Pick<AdminDatasourceMemoryDocument, 'title' | 'markdown_content' | 'source_overview'>
>

export type AdminThreadSummary = {
  thread_id: string
  datasource_id: string
  rolling_summary: string
  summary_status: string
  char_count: number
  recent_turn_count: number
  summarized_turn_count: number
  compression_count: number
  last_user_message: string | null
  last_assistant_message: string | null
  last_compacted_at: string | null
  created_at: string
  updated_at: string
}

type AdminThreadSummaryListResponse = {
  items: AdminThreadSummary[]
}

export type AdminDatasourceQaExample = {
  id: string
  datasource_id: string
  skill_pack_id: string | null
  question: string
  sql: string
  note: string
  scenario_tags: string[]
  source: string
  source_metadata: Record<string, unknown> | null
  embedding_status: string
  embedding_error: string | null
  embedding_updated_at: string | null
  created_at: string
  updated_at: string
}

type AdminDatasourceQaExampleListResponse = {
  items: AdminDatasourceQaExample[]
}

export type AdminSkillPackDetail = AdminSkillPackSummary & {
  business_overview: string | null
  schema_notes: string | null
  metrics: Record<string, unknown>[]
  entities: Record<string, unknown>[]
  business_rules: Record<string, unknown>[]
  pack_metadata: Record<string, unknown> | null
}

export type AdminSkillPackUpdateRequest = Partial<
  Pick<
    AdminSkillPackDetail,
    | 'name'
    | 'summary'
    | 'business_overview'
    | 'schema_notes'
    | 'status'
    | 'activation_mode'
    | 'confidence'
    | 'keywords'
    | 'table_focus'
    | 'business_rules'
  >
>

export type AdminSkillDocumentSummary = {
  id: number
  skill_pack_id: string
  document_type: string
  title: string
  content: string
  source: string | null
  weight: number
  document_metadata: Record<string, unknown> | null
  embedding_status: string
  embedding_error: string | null
  embedding_updated_at: string | null
  created_at: string
  updated_at: string
}

export type AdminSkillDocumentCreateRequest = {
  document_type: string
  title: string
  content: string
  source?: string | null
  weight?: number
  document_metadata?: Record<string, unknown> | null
}

export type AdminSkillDocumentUpdateRequest = Partial<AdminSkillDocumentCreateRequest>

export type DatasourceSchemaPayload = {
  dialect: string
  captured_at: string
  table_limit: number
  truncated: boolean
  table_count: number
  column_count: number
  tables: Array<{
    name: string
    comment?: string | null
    columns: Array<{
      name: string
      type: string
      nullable: boolean
      comment?: string | null
    }>
  }>
}

export type AdminSessionSummary = {
  thread_id: string
  first_user_message: string | null
  last_user_message: string | null
  turn_count: number
  created_at: string | null
  last_activity_at: string | null
}

type AdminSessionListResponse = {
  items: AdminSessionSummary[]
  limit: number
  offset: number
}

export type AdminExecutionSummary = {
  id: number
  thread_id: string | null
  datasource_id: string | null
  status: string
  rowcount: number | null
  error_message: string | null
  duration_ms: number | null
  sql_excerpt: string
  executed_at: string | null
}

export type AdminExecutionDetail = AdminExecutionSummary & {
  sql_text: string
}

type AdminExecutionListResponse = {
  items: AdminExecutionSummary[]
  limit: number
  offset: number
}

function parseSseBlock(block: string): { event: string; data: string } | null {
  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (dataLines.length === 0) return null
  return { event: eventName, data: dataLines.join('\n') }
}

async function readErrorMessage(res: Response): Promise<string> {
  const raw = await res.text()
  let parsed: unknown = null
  try {
    parsed = raw ? (JSON.parse(raw) as unknown) : null
  } catch {
    parsed = null
  }

  if (parsed && typeof parsed === 'object') {
    const obj = parsed as {
      detail?: unknown
      error?: { message?: unknown }
    }
    if (typeof obj.error?.message === 'string') {
      return obj.error.message
    }
    if (typeof obj.detail === 'string') {
      return obj.detail
    }
    if (obj.detail !== undefined) {
      return JSON.stringify(obj.detail)
    }
  }

  return raw || `HTTP ${res.status}`
}

async function fetchJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init)
  if (!res.ok) {
    throw new Error(await readErrorMessage(res))
  }
  return (await res.json()) as T
}

/**
 * POST SSE chat stream. Parses `event:` + `data:` frames from the backend.
 */
export async function streamChat(
  body: ChatStreamRequest,
  onEvent: (ev: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    throw new Error(await readErrorMessage(res))
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const raw of parts) {
      const block = raw.trim()
      if (!block) continue
      const parsed = parseSseBlock(block)
      if (!parsed) continue
      let data: unknown
      try {
        data = JSON.parse(parsed.data) as unknown
      } catch {
        data = parsed.data
      }
      onEvent({
        event: parsed.event as SseEventName,
        data,
      })
    }
  }
}

export async function runSql(body: ExecuteRequest): Promise<ExecuteResponse> {
  return fetchJson<ExecuteResponse>('/api/v1/execution/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function listDatasources(): Promise<DatasourceOption[]> {
  const payload = await fetchJson<DatasourceListResponse>(
    '/api/v1/execution/datasources',
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function listAdminDatasources(): Promise<AdminDatasourceSummary[]> {
  const payload = await fetchJson<AdminDatasourceListResponse>(
    '/api/v1/admin/datasources',
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function getAdminDatasource(
  datasourceId: string,
): Promise<AdminDatasourceDetail> {
  return fetchJson<AdminDatasourceDetail>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}`,
  )
}

export async function createAdminDatasource(
  body: AdminDatasourceCreateRequest,
): Promise<AdminDatasourceDetail> {
  return fetchJson<AdminDatasourceDetail>('/api/v1/admin/datasources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function updateAdminDatasource(
  datasourceId: string,
  body: AdminDatasourceUpdateRequest,
): Promise<AdminDatasourceDetail> {
  return fetchJson<AdminDatasourceDetail>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export async function deleteAdminDatasource(datasourceId: string): Promise<void> {
  const res = await fetch(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    throw new Error(await readErrorMessage(res))
  }
}

export async function testAdminDatasource(
  body: AdminDatasourceTestRequest,
): Promise<AdminDatasourceTestResponse> {
  return fetchJson<AdminDatasourceTestResponse>('/api/v1/admin/datasources/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function introspectAdminDatasource(
  datasourceId: string,
): Promise<AdminDatasourceIntrospectResponse> {
  return fetchJson<AdminDatasourceIntrospectResponse>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/introspect`,
    {
      method: 'POST',
    },
  )
}

export async function getAdminDatasourceSchema(
  datasourceId: string,
): Promise<DatasourceSchemaPayload> {
  return fetchJson<DatasourceSchemaPayload>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/schema`,
  )
}

export async function getAdminDatasourceProfile(
  datasourceId: string,
): Promise<AdminDatasourceProfile> {
  return fetchJson<AdminDatasourceProfile>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/profile`,
  )
}

export async function runAdminDatasourceOnboarding(
  datasourceId: string,
): Promise<AdminOnboardingRun> {
  return fetchJson<AdminOnboardingRun>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/onboarding/run`,
    {
      method: 'POST',
    },
  )
}

export async function getAdminDatasourceOnboardingRun(
  datasourceId: string,
): Promise<AdminOnboardingRun | null> {
  try {
    return await fetchJson<AdminOnboardingRun>(
      `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/onboarding/run`,
    )
  } catch (error) {
    if (error instanceof Error && error.message === 'datasource_onboarding_run_not_found') {
      return null
    }
    throw error
  }
}

export async function getAdminDatasourceAnalysisWorkspace(
  datasourceId: string,
  runId?: string,
): Promise<AdminAnalysisWorkspace> {
  const query = new URLSearchParams()
  if (runId) query.set('run_id', runId)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<AdminAnalysisWorkspace>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/analysis-workspace${suffix}`,
  )
}

export async function listAdminOnboardingRuns(
  datasourceId?: string,
  limit = 20,
): Promise<AdminOnboardingRun[]> {
  const query = new URLSearchParams()
  query.set('limit', String(limit))
  if (datasourceId) query.set('datasource_id', datasourceId)
  const payload = await fetchJson<{ items: AdminOnboardingRun[] }>(
    `/api/v1/admin/onboarding-runs?${query.toString()}`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function getAdminOnboardingRun(
  runId: string,
): Promise<AdminOnboardingRun> {
  return fetchJson<AdminOnboardingRun>(
    `/api/v1/admin/onboarding-runs/${encodeURIComponent(runId)}`,
  )
}

export async function getAdminDatasourceOnboardingContext(
  datasourceId: string,
): Promise<AdminOnboardingContext> {
  return fetchJson<AdminOnboardingContext>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/onboarding/context`,
  )
}

export async function updateAdminDatasourceOnboardingContext(
  datasourceId: string,
  body: { notes: string; questions: AdminOnboardingContextQuestion[] },
): Promise<AdminOnboardingContext> {
  return fetchJson<AdminOnboardingContext>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/onboarding/context`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export async function streamDatasourceOnboardingChat(
  datasourceId: string,
  body: { message?: string | null; run_id?: string | null },
  onEvent: (event: OnboardingChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/onboarding/chat/stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(body),
      signal,
    },
  )
  if (!res.ok) {
    throw new Error(await readErrorMessage(res))
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const raw of parts) {
      const parsed = parseSseBlock(raw.trim())
      if (!parsed) continue
      let data: unknown = parsed.data
      try {
        data = JSON.parse(parsed.data)
      } catch {
        data = parsed.data
      }
      if (parsed.event === 'step') onEvent({ event: 'step', data: data as Record<string, unknown> })
      if (parsed.event === 'message') onEvent({ event: 'message', data: data as { role: string; content: string } })
      if (parsed.event === 'question') onEvent({ event: 'question', data: data as OnboardingChatQuestion })
      if (parsed.event === 'done') onEvent({ event: 'done', data: data as { ok: boolean; should_rerun_analysis?: boolean } })
    }
  }
}

export async function listAdminSkillPacks(
  datasourceId?: string,
): Promise<AdminSkillPackSummary[]> {
  const query = datasourceId
    ? `?datasource_id=${encodeURIComponent(datasourceId)}`
    : ''
  const payload = await fetchJson<AdminSkillPackListResponse>(
    `/api/v1/admin/skill-packs${query}`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function getAdminMemoryDocument(
  datasourceId: string,
): Promise<AdminDatasourceMemoryDocument> {
  return fetchJson<AdminDatasourceMemoryDocument>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/memory-document`,
  )
}

export async function updateAdminMemoryDocument(
  datasourceId: string,
  body: AdminDatasourceMemoryDocumentUpdateRequest,
): Promise<AdminDatasourceMemoryDocument> {
  return fetchJson<AdminDatasourceMemoryDocument>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/memory-document`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export async function listAdminQaExamples(options?: {
  datasourceId?: string
}): Promise<AdminDatasourceQaExample[]> {
  const query = new URLSearchParams()
  if (options?.datasourceId) query.set('datasource_id', options.datasourceId)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const payload = await fetchJson<AdminDatasourceQaExampleListResponse>(
    `/api/v1/admin/qa-examples${suffix}`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function listAdminThreadSummaries(
  datasourceId: string,
): Promise<AdminThreadSummary[]> {
  const payload = await fetchJson<AdminThreadSummaryListResponse>(
    `/api/v1/admin/datasources/${encodeURIComponent(datasourceId)}/thread-summaries`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}


export async function listAdminSessions(
  limit = 10,
  offset = 0,
): Promise<AdminSessionSummary[]> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  const payload = await fetchJson<AdminSessionListResponse>(
    `/api/v1/admin/history/sessions?${query.toString()}`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function listAdminExecutions(options?: {
  limit?: number
  offset?: number
  status?: string
  threadId?: string
}): Promise<AdminExecutionSummary[]> {
  const query = new URLSearchParams({
    limit: String(options?.limit ?? 10),
    offset: String(options?.offset ?? 0),
  })
  if (options?.status) query.set('status', options.status)
  if (options?.threadId) query.set('thread_id', options.threadId)
  const payload = await fetchJson<AdminExecutionListResponse>(
    `/api/v1/admin/history/executions?${query.toString()}`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function getAdminExecution(
  executionId: number,
): Promise<AdminExecutionDetail> {
  return fetchJson<AdminExecutionDetail>(
    `/api/v1/admin/history/executions/${executionId}`,
  )
}

export type SuggestionsResponse = {
  items: string[]
  datasource_id: string | null
  is_fallback?: boolean
}

export async function fetchSuggestions(
  datasourceId?: string,
  count = 4,
): Promise<SuggestionsResponse> {
  const query = new URLSearchParams({ count: String(count) })
  if (datasourceId) query.set('datasource_id', datasourceId)
  return fetchJson<SuggestionsResponse>(
    `/api/v1/chat/suggestions?${query.toString()}`,
  )
}

export type ThreadTurnItem = {
  id: number
  datasource_id: string
  role: string
  content: string
  turn_metadata: Record<string, unknown> | null
  created_at: string | null
}

type ThreadTurnsListResponse = {
  thread_id: string
  items: ThreadTurnItem[]
}

export async function fetchThreadTurns(
  threadId: string,
): Promise<ThreadTurnItem[]> {
  const payload = await fetchJson<ThreadTurnsListResponse>(
    `/api/v1/chat/threads/${encodeURIComponent(threadId)}/turns`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function deleteAdminSession(threadId: string): Promise<void> {
  const res = await fetch(`/api/v1/admin/history/sessions/${encodeURIComponent(threadId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    throw new Error(await readErrorMessage(res))
  }
}

export async function getAdminSkillPackDetail(
  packId: string,
): Promise<AdminSkillPackDetail> {
  return fetchJson<AdminSkillPackDetail>(
    `/api/v1/admin/skill-packs/${encodeURIComponent(packId)}`,
  )
}

export async function updateAdminSkillPack(
  packId: string,
  body: AdminSkillPackUpdateRequest,
): Promise<AdminSkillPackDetail> {
  return fetchJson<AdminSkillPackDetail>(
    `/api/v1/admin/skill-packs/${encodeURIComponent(packId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export async function deleteAdminSkillPack(packId: string): Promise<void> {
  const res = await fetch(
    `/api/v1/admin/skill-packs/${encodeURIComponent(packId)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `删除失败 (${res.status})`)
  }
}

export async function listAdminSkillDocuments(
  packId: string,
): Promise<AdminSkillDocumentSummary[]> {
  const payload = await fetchJson<{ items: AdminSkillDocumentSummary[] }>(
    `/api/v1/admin/skill-packs/${encodeURIComponent(packId)}/documents`,
  )
  return Array.isArray(payload.items) ? payload.items : []
}

export async function createAdminSkillDocument(
  packId: string,
  body: AdminSkillDocumentCreateRequest,
): Promise<AdminSkillDocumentSummary> {
  return fetchJson<AdminSkillDocumentSummary>(
    `/api/v1/admin/skill-packs/${encodeURIComponent(packId)}/documents`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export async function updateAdminSkillDocument(
  docId: number,
  body: AdminSkillDocumentUpdateRequest,
): Promise<AdminSkillDocumentSummary> {
  return fetchJson<AdminSkillDocumentSummary>(
    `/api/v1/admin/skill-documents/${docId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export async function deleteAdminSkillDocument(docId: number): Promise<void> {
  const res = await fetch(`/api/v1/admin/skill-documents/${docId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    throw new Error(await readErrorMessage(res))
  }
}

// ---------------------------------------------------------------------------
// Turn feedback
// ---------------------------------------------------------------------------

export type TurnFeedbackRequest = {
  rating: 'positive' | 'negative'
  save_to_skill?: boolean
  comment?: string | null
}

export type TurnFeedbackResponse = {
  ok: boolean
  turn_id: number
  rating: string
  learning_triggered: boolean
}

export async function submitTurnFeedback(
  threadId: string,
  turnId: number,
  body: TurnFeedbackRequest,
): Promise<TurnFeedbackResponse> {
  return fetchJson<TurnFeedbackResponse>(
    `/api/v1/chat/threads/${encodeURIComponent(threadId)}/turns/${turnId}/feedback`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}
