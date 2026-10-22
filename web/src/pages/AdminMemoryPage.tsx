import { useEffect, useMemo, useState } from 'react'
import { ArrowsClockwise, FileText, ListBullets, PencilSimple } from '@phosphor-icons/react'
import { useSearchParams } from 'react-router-dom'

import type { AdminDatasourceMemoryDocument, AdminDatasourceSummary } from '@/lib/api'
import { getAdminMemoryDocument, listAdminDatasources } from '@/lib/api'
import { MessageResponse } from '@/components/ai-elements/message'
import { NoticeBanner } from '@/components/layout/notice-banner'
import { PageIntro } from '@/components/layout/page-intro'
import { ProductEmptyState } from '@/components/layout/product-empty-state'
import { ProductSelect } from '@/components/layout/product-select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { learningSourceLabel, memoryUpdateActionLabel } from '@/lib/semanticLabels'

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '暂无'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

export function AdminMemoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const datasourceId = searchParams.get('datasource_id') ?? ''

  const [datasources, setDatasources] = useState<AdminDatasourceSummary[]>([])
  const [document, setDocument] = useState<AdminDatasourceMemoryDocument | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void listAdminDatasources()
      .then((items) => {
        if (cancelled) return
        setDatasources(items)
        if (!datasourceId && items[0]) {
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev)
              next.set('datasource_id', items[0].id)
              return next
            },
            { replace: true },
          )
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载数据源失败')
      })
    return () => {
      cancelled = true
    }
  }, [datasourceId, setSearchParams])

  const loadDocument = async (showRefreshing = false) => {
    if (!datasourceId) return
    if (showRefreshing) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const doc = await getAdminMemoryDocument(datasourceId)
      setDocument(doc)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载主记忆失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    void loadDocument()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasourceId])

  const selectedDatasource = useMemo(
    () => datasources.find((item) => item.id === datasourceId) ?? null,
    [datasourceId, datasources],
  )
  const datasourceOptions = useMemo(
    () =>
      datasources.map((item) => ({
        value: item.id,
        label: item.display_name || item.id,
        description: item.id,
      })),
    [datasources],
  )
  const lastAutonomousUpdate = document?.recent_updates[0]?.updated_at ?? document?.updated_at

  return (
    <div className="space-y-6">
      <PageIntro
        eyebrow="主记忆文档"
        title="记忆"
        description="每个数据源只保留一份由 Agent 自主维护的主记忆。这里只读展示当前文档和最近自动更新痕迹，不再人工编辑。"
        actions={(
          <Button variant="outline" size="sm" onClick={() => void loadDocument(true)} disabled={refreshing || !datasourceId}>
            {refreshing ? <Spinner className="size-3.5" /> : <ArrowsClockwise className="size-3.5" />}
            刷新文档
          </Button>
        )}
        stats={[
          {
            title: selectedDatasource?.display_name ?? '未选择数据源',
            detail: datasourceId ? `当前对象：${datasourceId}` : '先选择一个数据源后查看主记忆。',
            icon: FileText,
          },
          {
            title: `${document?.item_count ?? 0} 条稳定记忆`,
            detail: '主记忆只保留极简、长期有效、可跨会话复用的条目。',
            icon: ListBullets,
          },
          {
            title: `${document?.recent_updates.length ?? 0} 次近期更新`,
            detail: '展示 Agent 最近自动补充或改写过的记忆痕迹。',
            icon: PencilSimple,
          },
          {
            title: formatDateTime(lastAutonomousUpdate),
            detail: '最近一次自动维护时间。',
            icon: ArrowsClockwise,
          },
        ]}
      />

      {error ? <NoticeBanner tone="danger">{error}</NoticeBanner> : null}

      <Card className="z-20 overflow-visible rounded-[1.65rem] bg-white/62 shadow-[0_14px_40px_rgba(17,24,39,0.05)]">
        <CardContent className="grid gap-3 p-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <div className="space-y-2 text-xs font-medium text-[var(--foreground)]">
            <span>数据源</span>
            <ProductSelect
              value={datasourceId}
              options={datasourceOptions}
              placeholder="选择数据源"
              onChange={(value) => {
                const next = new URLSearchParams(searchParams)
                next.set('datasource_id', value)
                setSearchParams(next, { replace: true })
              }}
            />
          </div>
          <div className="rounded-xl border border-[var(--line)] bg-white/54 px-4 py-3 text-sm text-[var(--foreground-soft)]">
            主记忆只保留长期有效的全局知识、关键表关系、统计口径和查询注意事项。它由后台 Agent 基于稳定高置信信号自动维护，SQL 问答案例继续沉淀到独立 QA 层。
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <Spinner className="size-5 text-[var(--foreground-soft)]" />
        </div>
      ) : !document ? (
        <ProductEmptyState
          icon={FileText}
          title="暂无主记忆文档"
          description="完成数据源分析或产生稳定运行信号后，Agent 会自动维护数据源主记忆。"
        />
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
            <Card className="bg-white/66">
              <CardHeader>
                <CardTitle>当前主记忆</CardTitle>
                <CardDescription>
                  这里展示 Agent 实际会读取到的 Markdown 主记忆组织方式。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="min-h-[540px] rounded-2xl border border-[var(--line)] bg-white/56 p-5">
                  <MessageResponse className="text-[13px] leading-7 text-[var(--foreground)]">
                    {document.markdown_content || '_当前主记忆为空_'}
                  </MessageResponse>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white/66">
              <CardHeader>
                <CardTitle>最近自动更新</CardTitle>
                <CardDescription>
                  只展示最近几次自动补充/改写，帮助你观察 Agent 如何持续维护这份主记忆。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {document.recent_updates.length > 0 ? (
                  document.recent_updates.map((item, index) => (
                    <div
                      key={`${item.title}-${item.updated_at ?? index}-${index}`}
                      className="rounded-2xl border border-[var(--line)] bg-white/56 px-4 py-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-[var(--foreground)]">{item.title}</div>
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
                          <Badge variant="outline" className="text-[10px]">
                            {memoryUpdateActionLabel(item.action)}
                          </Badge>
                          <span>{item.section}</span>
                          <span>{formatDateTime(item.updated_at)}</span>
                        </div>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--foreground)]">{item.content}</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-[var(--muted-foreground)]">
                        <Badge variant="outline" className="text-[10px]">
                          {learningSourceLabel(item.source)}
                        </Badge>
                        <span>类型：{item.memory_type}</span>
                        <span>置信度：{Math.round(item.confidence * 100)}%</span>
                        {item.thread_id ? <span>线程：{item.thread_id}</span> : null}
                      </div>
                      {item.change_summary ? (
                        <p className="mt-3 text-xs leading-6 text-[var(--foreground-soft)]">{item.change_summary}</p>
                      ) : null}
                      {item.source_excerpt ? (
                        <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-xs leading-6 text-[var(--foreground-soft)]">
                          触发依据：{item.source_excerpt}
                        </div>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <ProductEmptyState
                    icon={PencilSimple}
                    title="暂无自动更新"
                    description="当 Agent 捕获到稳定事实并写入主记忆后，会在这里展示更新痕迹。"
                    className="py-12"
                  />
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
            <Card className="bg-white/66">
              <CardHeader>
                <CardTitle>管理方式与大纲</CardTitle>
                <CardDescription>
                  帮助你理解这份主记忆如何被自动维护，以及当前有哪些章节。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-2xl border border-[var(--line)] bg-white/56 px-4 py-3 text-sm leading-6 text-[var(--foreground-soft)]">
                  <div className="font-medium text-[var(--foreground)]">模式：{document.management_mode}</div>
                  <div className="mt-2">{document.source_overview || '暂无来源说明。'}</div>
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-[var(--foreground)]">当前大纲</div>
                  <div className="space-y-2">
                    {document.structured_outline.length > 0 ? (
                      document.structured_outline.map((item, index) => {
                        const title = String(item.title ?? '')
                        const level = Number(item.level ?? 1)
                        return (
                          <div
                            key={`${title}-${index}`}
                            className="rounded-xl border border-[var(--line)] px-3 py-2 text-sm text-[var(--foreground-soft)]"
                            style={{ paddingLeft: `${12 + Math.max(0, level - 1) * 14}px` }}
                          >
                            {title || '未命名章节'}
                          </div>
                        )
                      })
                    ) : (
                      <div className="text-sm text-[var(--muted-foreground)]">保存后会自动生成章节大纲。</div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white/66">
              <CardHeader>
                <CardTitle>历史来源 / 证据</CardTitle>
                <CardDescription>
                  冷启动与后续维护会参考这些素材，但真正保留下来的内容由 Agent 自动压缩进主记忆条目。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {document.evidence_items.length > 0 ? (
                  document.evidence_items.map((item, index) => (
                    <div
                      key={`${item.kind}-${item.title}-${index}`}
                      className="rounded-2xl border border-[var(--line)] bg-white/56 px-4 py-4"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-[var(--foreground)]">{item.title}</div>
                        <div className="text-[11px] text-[var(--muted-foreground)]">
                          {item.kind} · {formatDateTime(item.updated_at)}
                        </div>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--foreground-soft)]">{item.excerpt}</p>
                    </div>
                  ))
                ) : (
                  <ProductEmptyState
                    icon={FileText}
                    title="暂无历史来源"
                    description="冷启动材料、历史证据或迁移来源会在这里辅助解释主记忆来源。"
                    className="py-10"
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
