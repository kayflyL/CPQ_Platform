import type { PortalSheetRow } from '@/api/portal'
import type { KpPart } from '@/api/serverConfig'

export type KpMatchKind = 'item_id' | 'exact' | 'fuzzy' | 'none'

export interface KpMatchResult {
  kind: KpMatchKind
  part?: KpPart
}

const STRIP_RE = /[\s\-_·.()\[\]（）【】/:：,，;；+*×xX]/g

// token 规范化（与后端 kp_repo.semantic_tokens 同口径）：品牌/模块噪声剔除、端口写法、
// 型号连写（kh-50000→kh50000）、单位归一（64GB→64g、4800MHz→4800）。
const BRAND_RE = /\b(?:nvidia|geforce|amd|intel|mellanox|broadcom|lsi|samsung|zhaoxin|huawei|hygon|phytium)\b|兆芯|华为|海光|飞腾|国产/g
const NOISE_RE = /network\s*card|adapter|含模块|含光模块|多模光模块|单模光模块|光模块|光卡|涡轮卡|涡轮|server\s+edition|显卡|处理器|内存条|supercap|超级电容|含电容|含电池|cachevault|掉电保护|支架|网卡|光口|电口|企业级|读取密集型|读密集型|写密集型|混合型|\becc\b|\bcache\b|\bib\b|roce|rdma/g
const PORT_RE = /双口|二口|双电口|四口|单口|(\d+)\s*口/g
const PORT_MAP: Record<string, string> = { 双口: '2port', 二口: '2port', 双电口: '2port', 四口: '4port', 单口: '1port' }
const FUSE_RE = /([a-z])[\-_.·]+([0-9])/g
const TOKEN_RE = /[a-z0-9]+(?:\.[0-9]+)?/g

const SIGNIFICANT_WORDS = new Set([
  'sata', 'sas', 'nvme', 'ssd', 'hdd', 'gpu', 'cpu', 'ddr', 'dimm',
  'rdimm', 'lrdimm', 'ecc', 'pcie', 'u2', 'm2', 'ocp',
])

function normText(value: unknown): string {
  return String(value ?? '').toLowerCase().replace(STRIP_RE, '').trim()
}

function tokenize(value: unknown): string[] {
  let s = String(value ?? '').toLowerCase().replace(/[（）]/g, ' ')
  s = s.replace(PORT_RE, (m, d: string | undefined) => ` ${d ? `${d}port` : PORT_MAP[m]} `)
  s = s.replace(FUSE_RE, '$1$2')
  s = s.replace(/(\d)\s*gb\b/g, '$1g').replace(/(\d)\s*tb\b/g, '$1t')
  s = s.replace(/([gt])b\/s/g, '$1')
  s = s.replace(/(\d{4,5})\s*(?:mts|mt\/s|mhz)\b/g, '$1')
  s = s.replace(/(\d(?:\.\d+)?)\s*ghz\b/g, '$1')
  s = s.replace(BRAND_RE, ' ').replace(NOISE_RE, ' ')
  const out = new Set<string>()
  for (const t of s.match(TOKEN_RE) || []) {
    const m = t.match(/^([a-z]+)(\d.+)$/)
    if (m) {
      out.add(m[1])
      out.add(m[2])
    } else {
      out.add(t)
    }
  }
  return [...out]
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
