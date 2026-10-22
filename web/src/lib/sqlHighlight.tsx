import type { ReactNode } from 'react'

const KEYWORDS = new Set(
  [
    'select',
    'from',
    'where',
    'group',
    'by',
    'order',
    'having',
    'limit',
    'offset',
    'join',
    'left',
    'right',
    'inner',
    'outer',
    'full',
    'cross',
    'on',
    'as',
    'and',
    'or',
    'not',
    'in',
    'is',
    'null',
    'like',
    'ilike',
    'between',
    'exists',
    'case',
    'when',
    'then',
    'else',
    'end',
    'distinct',
    'with',
    'union',
    'all',
    'insert',
    'into',
    'update',
    'delete',
    'create',
    'alter',
    'drop',
    'truncate',
    'values',
    'set',
    'returning',
    'over',
    'partition',
    'asc',
    'desc',
    'true',
    'false',
  ].map((item) => item.toLowerCase()),
)

const TOKEN_PATTERN = /(--.*$|\/\*[\s\S]*?\*\/|'(?:''|[^'])*'|"(?:[^"]|"")*"|\b\d+(?:\.\d+)?\b|\b[a-z_][a-z0-9_$]*\b|[(),.;=*<>+\-/])/gim

const INDENT = '  '
const MULTI_WORD_KEYWORDS = [
  ['group', 'by'],
  ['order', 'by'],
  ['left', 'join'],
  ['right', 'join'],
  ['inner', 'join'],
  ['full', 'join'],
  ['cross', 'join'],
  ['insert', 'into'],
  ['delete', 'from'],
  ['union', 'all'],
] as const

const MAJOR_CLAUSES = new Set([
  'SELECT',
  'FROM',
  'WHERE',
  'GROUP BY',
  'ORDER BY',
  'HAVING',
  'LIMIT',
  'OFFSET',
  'INSERT INTO',
  'UPDATE',
  'DELETE FROM',
  'VALUES',
  'SET',
  'RETURNING',
  'UNION',
  'UNION ALL',
])

const JOIN_CLAUSES = new Set(['JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'FULL JOIN', 'CROSS JOIN'])
const LIST_CLAUSES = new Set(['SELECT', 'GROUP BY', 'ORDER BY', 'SET'])
const INLINE_KEYWORDS = new Set(['ASC', 'DESC', 'AS', 'ON'])

type Token = {
  value: string
  lower: string
  word: boolean
}

function tokenizeSql(sql: string): Token[] {
  const tokens: Token[] = []
  let match: RegExpExecArray | null

  TOKEN_PATTERN.lastIndex = 0
  while ((match = TOKEN_PATTERN.exec(sql)) !== null) {
    const value = match[0]
    tokens.push({
      value,
      lower: value.toLowerCase(),
      word: /^[_a-z][_a-z0-9$]*$/i.test(value),
    })
  }

  return tokens
}

function combineKeywordPhrases(tokens: Token[]): Token[] {
  const combined: Token[] = []

  for (let index = 0; index < tokens.length; index += 1) {
    const current = tokens[index]
    let matched = false

    if (current.word) {
      for (const phrase of MULTI_WORD_KEYWORDS) {
        const slice = tokens.slice(index, index + phrase.length)
        if (slice.length === phrase.length && slice.every((token, phraseIndex) => token.lower === phrase[phraseIndex])) {
          const value = phrase.map((part) => part.toUpperCase()).join(' ')
          combined.push({ value, lower: value.toLowerCase(), word: true })
          index += phrase.length - 1
          matched = true
          break
        }
      }
    }

    if (!matched) {
      combined.push(current.word ? { ...current, value: current.value.toUpperCase() } : current)
    }
  }

  return combined
}

function tokenClass(token: string): string {
  if (token.startsWith('--') || token.startsWith('/*')) {
    return 'text-[color-mix(in_srgb,var(--muted-foreground)_88%,var(--card))] italic'
  }
  if (token.startsWith("'") || token.startsWith('"')) {
    return 'text-[oklch(0.46_0.08_145)]'
  }
  if (/^\d/.test(token)) {
    return 'text-[oklch(0.54_0.16_285)]'
  }
  if (/^[(),.;=*<>+\-/]$/.test(token)) {
    return 'text-[color-mix(in_srgb,var(--foreground)_70%,transparent)]'
  }
  if (KEYWORDS.has(token.toLowerCase())) {
    return 'font-semibold text-[oklch(0.56_0.16_250)]'
  }
  return 'text-[var(--foreground)]'
}

function needsSpaceBefore(next: string, previous: string | null): boolean {
  if (!previous) return false
  if (next === ',' || next === ')' || next === ';') return false
  if (previous === '(') return false
  if (previous === '.') return false
  if (next === '.') return false
  return true
}

function pushLine(lines: string[], line: string): void {
  const trimmed = line.trimEnd()
  if (trimmed) lines.push(trimmed)
}

export function formatSqlForDisplay(sql: string): string {
  const logicalTokens = combineKeywordPhrases(tokenizeSql(sql.trim()))
  if (logicalTokens.length === 0) return ''

  const lines: string[] = []
  let line = ''
  let parenDepth = 0
  let clause: string | null = null
  let previous: string | null = null

  const startLine = (level: number, token: string) => {
    pushLine(lines, line)
    line = `${INDENT.repeat(Math.max(level, 0))}${token}`
  }

  for (const token of logicalTokens) {
    const value = token.value
    const upper = token.word ? value.toUpperCase() : value
    const atTopLevel = parenDepth === 0

    if (value === ')') {
      parenDepth = Math.max(parenDepth - 1, 0)
    }

    if (token.word && atTopLevel && MAJOR_CLAUSES.has(upper)) {
      clause = upper
      startLine(0, upper)
      previous = upper
      continue
    }

    if (token.word && atTopLevel && JOIN_CLAUSES.has(upper)) {
      clause = upper
      startLine(1, upper)
      previous = upper
      continue
    }

    if (token.word && atTopLevel && (upper === 'AND' || upper === 'OR') && (clause === 'WHERE' || clause === 'HAVING')) {
      startLine(1, upper)
      previous = upper
      continue
    }

    if (value === ',' && atTopLevel && clause && LIST_CLAUSES.has(clause)) {
      line += ','
      pushLine(lines, line)
      line = `${INDENT.repeat(1)}`
      previous = ','
      continue
    }

    if (value === ',' && atTopLevel && clause === 'FROM') {
      line += ','
      pushLine(lines, line)
      line = `${INDENT.repeat(1)}`
      previous = ','
      continue
    }

    if (value === '(') {
      if (needsSpaceBefore(value, previous)) {
        line += ' '
      }
      line += value
      parenDepth += 1
      previous = value
      continue
    }

    if (needsSpaceBefore(value, previous)) {
      line += ' '
    }
    line += value

    if (value === ';') {
      pushLine(lines, line)
      line = ''
    }

    if (token.word && INLINE_KEYWORDS.has(upper)) {
      previous = upper
    } else {
      previous = value
    }
  }

  pushLine(lines, line)
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

export function renderHighlightedSql(sql: string): ReactNode[] {
  const chunks: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  TOKEN_PATTERN.lastIndex = 0

  while ((match = TOKEN_PATTERN.exec(sql)) !== null) {
    if (match.index > lastIndex) {
      chunks.push(sql.slice(lastIndex, match.index))
    }

    const token = match[0]
    chunks.push(
      <span key={`${match.index}-${token}`} className={tokenClass(token)}>
        {token}
      </span>,
    )
    lastIndex = match.index + token.length
  }

  if (lastIndex < sql.length) {
    chunks.push(sql.slice(lastIndex))
  }

  return chunks
}
