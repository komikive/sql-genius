import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  BookOpenText,
  Brain,
  CheckCircle,
  Database,
  FileText,
  FloppyDisk,
  Gauge,
  NotePencil,
  Sparkle,
  Tag,
  Trash,
} from '@phosphor-icons/react'

import type {
  AdminSkillDocumentSummary,
  AdminSkillPackDetail,
  AdminSkillPackUpdateRequest,
} from '@/lib/api'
import {
  createAdminSkillDocument,
  deleteAdminSkillPack,
  getAdminSkillPackDetail,
  listAdminSkillDocuments,
  updateAdminSkillDocument,
  updateAdminSkillPack,
} from '@/lib/api'
import FadeContent from '@/components/FadeContent'
import { NoticeBanner } from '@/components/layout/notice-banner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'

function documentTypeLabel(value: string): string {
  switch (value) {
    case 'canonical': return '技能主文档'
    case 'overview': return '主文档'
    case 'reference': return '参考'
    case 'schema-note': return '结构说明'
    case 'business-rule': return '业务规则'
    case 'example-sql': return '示例 SQL'
    default: return value
  }
}

function embeddingStatusLabel(value: string): string {
  switch (value) {
    case 'ready': return '已向量化'
    case 'pending': return '待向量化'
    case 'failed': return '向量化失败'
    default: return value
  }
}

function originLabel(value: string): string {
  if (value === 'onboarding') return '初始化'
  if (value === 'runtime-learning') return '运行时'
  if (value === 'system') return '系统'
  return value
}

function splitList(value: string): string[] {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function SoftStat({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string
  icon: typeof Brain
}) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_86%,white)] px-3.5 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
      <div className="flex items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
        <Icon className="size-3.5 text-[var(--primary)]" />
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold tracking-[-0.02em] text-[var(--foreground)]">{value}</div>
    </div>
  )
}

function SectionTitle({
  eyebrow,
  title,
  description,
  icon: Icon,
}: {
  eyebrow: string
  title: string
  description: string
  icon: typeof Brain
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--primary)]">
        <Icon className="size-4" />
      </div>
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
          {eyebrow}
        </div>
        <h2 className="mt-1 text-base font-semibold tracking-[-0.03em] text-[var(--foreground)]">{title}</h2>
        <p className="mt-1 max-w-[72ch] text-xs leading-5 text-[var(--foreground-soft)]">{description}</p>
      </div>
    </div>
  )
}

export function SkillPackDetailPage() {
  const { id: legacyDatasourceId, packId } = useParams<{ id?: string; packId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [pack, setPack] = useState<AdminSkillPackDetail | null>(null)
  const [docs, setDocs] = useState<AdminSkillDocumentSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    if (!packId) return
    setLoading(true)
    setError(null)
    try {
      const [nextPack, nextDocs] = await Promise.all([
        getAdminSkillPackDetail(packId),
        listAdminSkillDocuments(packId),
      ])
      setPack(nextPack)
      setDocs(nextDocs)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载技能详情失败')
    } finally {
      setLoading(false)
    }
  }, [packId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const datasourceId = pack?.datasource_id ?? legacyDatasourceId ?? searchParams.get('datasource_id') ?? ''
  const backHref = `/admin/skills${datasourceId ? `?datasource_id=${encodeURIComponent(datasourceId)}` : ''}`
  const canonicalDoc = useMemo(
    () => docs.find((doc) => doc.document_type === 'canonical')
      ?? docs.find((doc) => doc.document_type === 'overview')
      ?? docs[0]
      ?? null,
    [docs],
  )
  const legacyDocCount = canonicalDoc ? docs.filter((doc) => doc.id !== canonicalDoc.id).length : docs.length

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="size-5 text-[var(--foreground-soft)]" />
      </div>
    )
  }

  if (!pack) {
    return (
      <div className="py-24 text-center text-sm text-[var(--foreground-soft)]">
        技能包未找到。
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="relative overflow-hidden rounded-[32px] border border-[var(--line)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--surface)_94%,white),color-mix(in_srgb,var(--primary)_5%,white))] px-6 py-6 shadow-[0_30px_80px_rgba(15,23,42,0.07)]">
        <div className="pointer-events-none absolute -right-20 -top-24 size-56 rounded-full bg-[color-mix(in_srgb,var(--primary)_12%,transparent)] blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 left-1/3 h-24 w-72 rounded-full bg-white/60 blur-3xl" />

        <div className="relative space-y-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              onClick={() => navigate(backHref)}
              className="inline-flex w-fit items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium text-[var(--foreground-soft)] transition-colors hover:bg-white/60 hover:text-[var(--foreground)]"
            >
              <ArrowLeft className="size-3.5" />
              返回技能目录
            </button>

            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {datasourceId ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/admin/datasources/${encodeURIComponent(datasourceId)}`)}
                  className="bg-white/70"
                >
                  <Database className="size-3.5" />
                  前往数据源
                </Button>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                disabled={deleting}
                className="bg-white/70 text-red-500 hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                onClick={async () => {
                  if (!window.confirm(`确定删除技能包「${pack.name}」？此操作不可恢复。`)) return
                  setDeleting(true)
                  try {
                    await deleteAdminSkillPack(pack.id)
                    navigate(backHref)
                  } catch (err) {
                    setError(err instanceof Error ? err.message : '删除失败')
                    setDeleting(false)
                  }
                }}
              >
                {deleting ? <Spinner className="size-3.5" /> : <Trash className="size-3.5" />}
                删除技能
              </Button>
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-end">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-white/70 px-3 py-1 text-[11px] font-medium text-[var(--foreground-soft)] shadow-[0_8px_20px_rgba(15,23,42,0.04)]">
                <Sparkle className="size-3.5 text-[var(--primary)]" />
                技能资产详情
              </div>
              <div className="space-y-2">
                <h1 className="text-[30px] font-semibold tracking-[-0.045em] text-[var(--foreground)]">
                  {pack.name}
                </h1>
                <p className="max-w-[72ch] text-[14px] leading-7 text-[var(--foreground-soft)]">
                  将技能拆成两个清晰层次：上方索引用来召回，下方主文档承载 Agent 真正读取的业务方法、指标口径和 Join 规则。
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2.5 text-xs text-[var(--foreground-soft)]">
                <Badge variant="outline">来源：{originLabel(pack.origin)}</Badge>
                <Badge variant="outline">{pack.activation_mode.toUpperCase()}</Badge>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <SoftStat label="置信度" value={`${Math.round(pack.confidence * 100)}%`} icon={Gauge} />
              <SoftStat label="主文档" value={canonicalDoc ? '已建立' : '待生成'} icon={BookOpenText} />
              <SoftStat label="历史材料" value={`${legacyDocCount} 份`} icon={FileText} />
            </div>
          </div>
        </div>
      </div>

      {error ? <NoticeBanner tone="danger">{error}</NoticeBanner> : null}

      <div className="space-y-4">
        <MetadataEditor
          pack={pack}
          onSave={async (body) => {
            const updated = await updateAdminSkillPack(pack.id, body)
            setPack(updated)
          }}
        />

        <CanonicalDocumentEditor
          doc={canonicalDoc}
          packId={pack.id}
          packName={pack.name}
          legacyDocCount={legacyDocCount}
          onRefresh={loadData}
        />
      </div>
    </div>
  )
}

/* ---------- Metadata Editor ---------- */

function MetadataEditor({
  pack,
  onSave,
}: {
  pack: AdminSkillPackDetail
  onSave: (body: AdminSkillPackUpdateRequest) => Promise<void>
}) {
  const [name, setName] = useState(pack.name)
  const [summary, setSummary] = useState(pack.summary)
  const [confidence, setConfidence] = useState(String(pack.confidence))
  const [keywords, setKeywords] = useState(pack.keywords.join(', '))
  const [tableFocus, setTableFocus] = useState(pack.table_focus.join('\n'))
  const [saving, setSaving] = useState(false)
  const keywordItems = useMemo(() => splitList(keywords).slice(0, 12), [keywords])
  const tableItems = useMemo(() => splitList(tableFocus).slice(0, 12), [tableFocus])

  useEffect(() => {
    setName(pack.name)
    setSummary(pack.summary)
    setConfidence(String(pack.confidence))
    setKeywords(pack.keywords.join(', '))
    setTableFocus(pack.table_focus.join('\n'))
  }, [pack])

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave({
        name: name.trim(),
        summary: summary.trim(),
        confidence: Number(confidence) || pack.confidence,
        keywords: splitList(keywords),
        table_focus: splitList(tableFocus),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="overflow-hidden rounded-[28px] border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_92%,white)] shadow-[0_18px_52px_rgba(15,23,42,0.045)]">
      <CardHeader className="border-b border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_64%,white)] px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <SectionTitle
            eyebrow="Index Layer"
            title="技能索引"
            description="只维护用于召回、排序和治理的轻量字段。正文知识全部沉到下方主文档，减少多处编辑。"
            icon={Brain}
          />
          <Button size="sm" onClick={() => void handleSave()} disabled={saving} className="lg:mt-1">
            {saving ? <Spinner className="size-3.5" /> : <FloppyDisk className="size-3.5" />}
            保存索引
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_360px]">
          <div className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_160px]">
              <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
                <span>技能名称</span>
                <Input value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
                <span>置信度</span>
                <Input
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={confidence}
                  onChange={(event) => setConfidence(event.target.value)}
                />
              </label>
            </div>

            <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
              <span>摘要</span>
              <Textarea
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                className="min-h-[96px] resize-none leading-6"
              />
            </label>

            <div className="grid gap-4 lg:grid-cols-2">
              <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
                <span>关键词</span>
                <Input
                  value={keywords}
                  onChange={(event) => setKeywords(event.target.value)}
                  placeholder="用逗号分隔，如 GMV、客单价、折扣"
                />
              </label>
              <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
                <span>表焦点</span>
                <Textarea
                  value={tableFocus}
                  onChange={(event) => setTableFocus(event.target.value)}
                  className="min-h-[92px] font-mono text-xs leading-5"
                  placeholder="每行一个表名"
                />
              </label>
            </div>
          </div>

          <aside className="space-y-3 rounded-3xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_70%,white)] p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <Tag className="size-4 text-[var(--primary)]" />
              召回预览
            </div>
            <div className="space-y-3">
              <div>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">关键词</div>
                <div className="flex flex-wrap gap-1.5">
                  {keywordItems.length > 0 ? keywordItems.map((item) => (
                    <span key={item} className="rounded-full bg-white/78 px-2.5 py-1 text-[11px] text-[var(--foreground-soft)] ring-1 ring-[var(--line)]">
                      {item}
                    </span>
                  )) : <span className="text-xs text-[var(--muted-foreground)]">尚未填写</span>}
                </div>
              </div>
              <div>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">重点表</div>
                <div className="grid gap-1.5">
                  {tableItems.length > 0 ? tableItems.map((item) => (
                    <div key={item} className="flex items-center gap-2 rounded-xl bg-white/72 px-2.5 py-1.5 font-mono text-[11px] text-[var(--foreground)] ring-1 ring-[var(--line)]">
                      <span className="size-1.5 rounded-full bg-[var(--primary)]" />
                      {item}
                    </div>
                  )) : <span className="text-xs text-[var(--muted-foreground)]">尚未填写</span>}
                </div>
              </div>
            </div>
            <div className="rounded-2xl border border-[color-mix(in_srgb,var(--primary)_16%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_4%,white)] px-3 py-3 text-xs leading-5 text-[var(--foreground-soft)]">
              索引只帮助 Agent 快速定位技能；指标口径、Join 路径和易错点请统一维护在下方 Markdown 主文档。
            </div>
          </aside>
        </div>
      </CardContent>
    </Card>
  )
}

/* ---------- Canonical Skill Document ---------- */

function CanonicalDocumentEditor({
  doc,
  packId,
  packName,
  legacyDocCount,
  onRefresh,
}: {
  doc: AdminSkillDocumentSummary | null
  packId: string
  packName: string
  legacyDocCount: number
  onRefresh: () => Promise<void>
}) {
  const [title, setTitle] = useState(doc?.title ?? `${packName} 技能主文档`)
  const [content, setContent] = useState(doc?.content ?? '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setTitle(doc?.title ?? `${packName} 技能主文档`)
    setContent(doc?.content ?? '')
  }, [doc, packName])

  const handleSave = async () => {
    setSaving(true)
    try {
      if (doc) {
        await updateAdminSkillDocument(doc.id, {
          title: title.trim(),
          content: content.trim(),
          document_type: 'canonical',
          source: doc.source ?? 'admin-skill-studio',
          weight: Math.max(doc.weight || 1, 2),
          document_metadata: {
            ...(doc.document_metadata ?? {}),
            canonical: true,
          },
        })
      } else {
        await createAdminSkillDocument(packId, {
          title: title.trim() || `${packName} 技能主文档`,
          content: content.trim(),
          document_type: 'canonical',
          source: 'admin-skill-studio',
          weight: 2,
          document_metadata: { canonical: true },
        })
      }
      await onRefresh()
    } finally {
      setSaving(false)
    }
  }

  return (
    <FadeContent duration={400}>
      <Card className="overflow-hidden rounded-[28px] border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_94%,white)] shadow-[0_18px_52px_rgba(15,23,42,0.045)]">
        <CardHeader className="border-b border-[var(--line)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--surface-strong)_70%,white),white)] px-5 py-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <SectionTitle
              eyebrow="Runtime Playbook"
              title="技能主文档"
              description="运行时读取的唯一 Markdown 文档。业务目标、指标口径、Join 方法、易错点和规则都在这里维护。"
              icon={BookOpenText}
            />
            <div className="flex flex-wrap justify-end gap-2">
              <Badge variant="outline">{doc ? documentTypeLabel(doc.document_type) : '待创建'}</Badge>
              {doc ? (
                <Badge variant={doc.embedding_status === 'ready' ? 'default' : 'outline'}>
                  {embeddingStatusLabel(doc.embedding_status)}
                </Badge>
              ) : null}
            </div>
          </div>
          {legacyDocCount > 0 ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-700">
              检测到 {legacyDocCount} 份历史补充文档。新的运行时优先读取技能主文档；如其中有有效内容，建议整理进本文档。
            </div>
          ) : null}
        </CardHeader>
        <CardContent className="p-5">
          <div className="grid gap-5 xl:grid-cols-[260px_minmax(0,1fr)]">
            <aside className="space-y-4 rounded-3xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_70%,white)] p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
                <NotePencil className="size-4 text-[var(--primary)]" />
                推荐结构
              </div>
              <div className="space-y-2">
                {['技能摘要', '业务目标', '核心表', '表结构与 Join 口径', '指标口径', '业务规则与易错点'].map((item, index) => (
                  <div key={item} className="flex items-center gap-2 rounded-2xl bg-white/72 px-3 py-2 text-xs text-[var(--foreground-soft)] ring-1 ring-[var(--line)]">
                    <span className="flex size-5 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_9%,white)] text-[10px] font-semibold text-[var(--primary)]">
                      {index + 1}
                    </span>
                    {item}
                  </div>
                ))}
              </div>
              <div className="rounded-2xl border border-[color-mix(in_srgb,var(--primary)_16%,var(--line))] bg-[color-mix(in_srgb,var(--primary)_4%,white)] px-3 py-3 text-xs leading-5 text-[var(--foreground-soft)]">
                QA 示例与主记忆仍然独立维护，不写入技能主文档。这里专注保存稳定查询方法。
              </div>
            </aside>

            <div className="space-y-4">
              <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
                <span>文档标题</span>
                <Input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label className="space-y-2 text-xs font-medium text-[var(--foreground)]">
                <span>Markdown 内容</span>
                <Textarea
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  className="min-h-[560px] rounded-3xl bg-[color-mix(in_srgb,var(--surface-strong)_52%,white)] p-4 font-mono text-xs leading-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]"
                  placeholder={`# ${packName}\n\n## 技能摘要\n\n## 业务目标\n\n## 核心表\n\n## 表结构与 Join 口径\n\n## 指标口径\n\n## 业务规则与易错点`}
                />
              </label>
              <div className="flex flex-col gap-3 rounded-3xl border border-[var(--line)] bg-[color-mix(in_srgb,var(--surface-strong)_62%,white)] px-4 py-3 text-sm text-[var(--foreground-soft)] lg:flex-row lg:items-center lg:justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle className="size-4 text-[var(--primary)]" />
                  <span>保存后将标记为待向量化，下一次嵌入刷新后进入检索主路径。</span>
                </div>
                <Button size="sm" onClick={() => void handleSave()} disabled={saving || !content.trim()}>
                  {saving ? <Spinner className="size-3.5" /> : <FloppyDisk className="size-3.5" />}
                  保存主文档
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </FadeContent>
  )
}
