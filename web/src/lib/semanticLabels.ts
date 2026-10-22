export function learningSourceLabel(source: string): string {
  const normalized = source.toLowerCase()
  if (normalized.includes('runtime')) return '🤖 运行时学习'
  if (normalized.includes('feedback')) return '💬 用户反馈'
  if (normalized.includes('review') || normalized.includes('approve')) return '🧪 审批晋升'
  if (normalized.includes('auto') || normalized.includes('learning')) return '✨ 自动沉淀'
  return `📝 ${source}`
}

export function embeddingStatusLabel(status: string): string {
  const normalized = status.toLowerCase()
  if (normalized === 'ready') return '🧠 向量就绪'
  if (normalized === 'pending') return '⏳ 向量处理中'
  if (normalized === 'error' || normalized === 'failed') return '⚠️ 向量异常'
  return `🔹 ${status}`
}

export function memoryUpdateActionLabel(action: string): string {
  const normalized = action.toLowerCase()
  if (normalized.includes('replace') || normalized.includes('rewrite')) return '♻️ 主记忆改写'
  if (normalized.includes('add') || normalized.includes('create')) return '➕ 主记忆新增'
  return `📝 ${action}`
}

export function memoryBadgeLabel(count: number): string {
  return `🧠 记忆命中 ${count}`
}

export function historyBadgeLabel(count: number): string {
  return `🕘 历史命中 ${count}`
}

export function evidenceBadgeLabel(count: number): string {
  return `🔎 证据检索 ${count}`
}

export function sourceCategoryLabel(title: string): string {
  const normalized = title.toLowerCase()
  if (normalized.includes('memory') || normalized.includes('记忆')) return '🧠 记忆命中'
  if (normalized.includes('skill') || normalized.includes('技能')) return '📚 技能激活'
  if (normalized.includes('history') || normalized.includes('历史') || normalized.includes('thread')) return '🕘 历史命中'
  if (normalized.includes('schema') || normalized.includes('table') || normalized.includes('字段')) return '🗂️ 结构证据'
  return '🔎 证据检索'
}
