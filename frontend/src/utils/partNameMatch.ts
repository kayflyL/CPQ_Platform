import type { PortalSheetRow } from '@/api/portal'
import type { KpPart } from '@/api/serverConfig'

export type KpMatchKind = 'item_id' | 'exact' | 'fuzzy' | 'none'

export interface KpMatchResult {
  kind: KpMatchKind
  part?: KpPart
}

const STRIP_RE = /[\s\-_·.()\[\]（）【】/:：,，;；+*×xX]/g
const SPLIT_RE = /[\s\-_·.()\[\]（）【】/:：,，;；+*×xX]+/g
const UNIT_MERGE_RE = /(\d+(?:\.\d+)?)\s*(t|tb|g|gb|m|mb|mhz|ghz|w|rpm|v)\b/g

const SIGNIFICANT_WORDS = new Set([
  'sata', 'sas', 'nvme', 'ssd', 'hdd', 'gpu', 'cpu', 'ddr', 'dimm',
  'rdimm', 'lrdimm', 'ecc', 'pcie', 'u.2', 'm.2', 'ocp',
])

function normText(value: unknown): string {
  return String(value ?? '').toLowerCase().replace(STRIP_RE, '').trim()
}

function tokenize(value: unknown): string[] {
  const merged = String(value ?? '').toLowerCase().replace(UNIT_MERGE_RE, '$1$2')
  return merged
    .split(SPLIT_RE)
    .map((token) => token.trim())
    .filter(Boolean)
}

function isSignificant(token: string): boolean {
  return /\d/.test(token) || SIGNIFICANT_WORDS.has(token)
}

function candidateTokens(part: KpPart): Set<string> {
  return new Set(tokenize([part.name, part.pn, part.category].filter(Boolean).join(' ')))
}

function scorePart(text: string, part: KpPart): number {
  if (!text) return 0
  const inputTokens = tokenize(text)
  if (!inputTokens.length) return 0

  const exactNames = [part.name, part.pn].filter(Boolean)
  if (exactNames.some((name) => normText(name) === normText(text))) return 1

  const partTokens = candidateTokens(part)
  const missingSignificant = inputTokens.filter((token) => isSignificant(token) && !partTokens.has(token))
  if (missingSignificant.length) return 0

  const normalizedText = normText(text)
  const hasInclusion = exactNames.some((name) => {
    const normalizedName = normText(name)
    return normalizedName && (normalizedName.includes(normalizedText) || normalizedText.includes(normalizedName))
  })

  const intersection = inputTokens.filter((token) => partTokens.has(token)).length
  const union = new Set([...inputTokens, ...partTokens]).size
  const jaccard = union ? intersection / union : 0
  return hasInclusion ? Math.max(jaccard, 0.95) : jaccard
}

function bestFuzzy(text: string, parts: KpPart[], threshold: number): KpPart | undefined {
  let bestPart: KpPart | undefined
  let bestScore = 0
  for (const part of parts) {
    const score = scorePart(text, part)
    if (score > bestScore) {
      bestScore = score
      bestPart = part
    }
  }
  return bestScore >= threshold ? bestPart : undefined
}

function exactPart(text: string, parts: KpPart[]): KpPart | undefined {
  const normalized = normText(text)
  if (!normalized) return undefined
  return parts.find((part) => normText(part.name) === normalized || normText(part.pn) === normalized)
}

function categoryParts(row: PortalSheetRow, parts: KpPart[]): KpPart[] {
  const category = normText(row.part_category)
  if (!category) return []
  return parts.filter((part) => normText(part.category) === category)
}

export function matchKpPart(row: PortalSheetRow, parts: KpPart[]): KpMatchResult {
  const list = Array.isArray(parts) ? parts : []

  if (row.item_id != null) {
    const byId = list.find((part) => part.id != null && String(part.id) === String(row.item_id))
    if (byId) return { kind: 'item_id', part: byId }
  }

  const text = [row.catalogue, row.description].filter(Boolean).join(' ')
  const scoped = categoryParts(row, list)

  const scopedExact = exactPart(text, scoped)
  if (scopedExact) return { kind: 'exact', part: scopedExact }

  const globalExact = exactPart(text, list)
  if (globalExact) return { kind: 'exact', part: globalExact }

  const inputTokens = tokenize(text)
  const specificEnough = inputTokens.length >= 2 || (inputTokens.length === 1 && /\d/.test(inputTokens[0]))
  if (!specificEnough) return { kind: 'none' }

  const scopedFuzzy = bestFuzzy(text, scoped.length ? scoped : list, 0.55)
  if (scopedFuzzy) return { kind: 'fuzzy', part: scopedFuzzy }

  const globalFuzzy = bestFuzzy(text, list, 0.6)
  if (globalFuzzy) return { kind: 'fuzzy', part: globalFuzzy }

  return { kind: 'none' }
}

export function suggestKpParts(row: PortalSheetRow, parts: KpPart[], limit = 3): KpPart[] {
  const list = Array.isArray(parts) ? parts : []
  const text = [row.catalogue, row.description].filter(Boolean).join(' ')
  const scoped = categoryParts(row, list)
  const pool = scoped.length ? scoped : list
  const ranked = pool
    .map((part) => ({ part, score: scorePart(text, part) }))
    .filter((item) => item.score > 0.3)
    .sort((a, b) => b.score - a.score)

  const seen = new Set<number | string>()
  const out: KpPart[] = []
  for (const item of ranked) {
    const key = item.part.id ?? item.part.pn
    if (seen.has(key)) continue
    seen.add(key)
    out.push(item.part)
    if (out.length >= limit) break
  }
  return out
}
