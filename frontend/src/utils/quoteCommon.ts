/** 商机详情 / 报价工作台共用纯函数。避免金额、日期、KP 比价状态在各组件重复实现。 */

export function formatDate(dateStr?: string): string {
  if (!dateStr) return '-'
  const slice = dateStr.slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(slice) ? slice : dateStr
}

export function formatPrice(price?: number | null): string {
  if (!price) return '0.00'
  return price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function marginBadgeClass(margin?: number | null): string {
  if (margin == null) return 'badge-neutral'
  if (margin >= 10) return 'badge-high'
  if (margin >= 0) return 'badge-mid'
  return 'badge-low'
}

export function fmtTime(value?: string): string {
  if (!value) return '—'
  return value.length >= 16 ? value.slice(5, 16) : value
}

export function money(value?: number | null): string {
  return `¥${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

export function currencySymbol(c: unknown): string {
  return (String(c || '').toUpperCase()) === 'USD' ? '$' : '¥'
}

export function toFiniteNumber(value: unknown, fallback = 0): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

export function calcUnitCost(
  basePrice: unknown,
  currency: unknown,
  exchangeRate: number,
  taxRate: number,
): number {
  const base = toFiniteNumber(basePrice)
  return String(currency || '').toUpperCase() === 'USD'
    ? base * exchangeRate * (1 + taxRate)
    : base
}

export function calcUnitSales(
  basePrice: unknown,
  currency: unknown,
  profitMargin: unknown,
  exchangeRate: number,
  taxRate: number,
): number {
  const margin = toFiniteNumber(profitMargin)
  return calcUnitCost(basePrice, currency, exchangeRate, taxRate) * (1 + margin / 100)
}

/** calcUnitCost 的逆变换：把工作台统一显示的 RMB 含税单价还原回行原币种 base_price
 *  （RMB 行原值即含税价；USD 行 = RMB ÷ 汇率 ÷ (1+税率)）。手工补价入口共用；
 *  USD 行不取整，保证按显示值回填后再显示不漂。 */
export function rmbToBasePrice(
  rmbCost: unknown,
  currency: unknown,
  exchangeRate: number,
  taxRate: number,
): number {
  const rmb = toFiniteNumber(rmbCost)
  if (String(currency || '').toUpperCase() !== 'USD') return Math.round(rmb * 100) / 100
  const factor = (toFiniteNumber(exchangeRate, 1) || 1) * (1 + toFiniteNumber(taxRate))
  return factor > 0 ? rmb / factor : 0
}

export function safeServerModelFilename(model?: string | null): string {
  const cleaned = String(model || '')
    .trim()
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
  return cleaned || '未选机型'
}

export function dbPriceOf(item: { db_price?: unknown }): number | null {
  const raw = item.db_price
  if (raw === '' || raw == null) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

export function kpSyncable(item: {
  catalogue?: string
  base_price?: number | string | null
  db_price?: unknown
}): boolean {
  const model = item.catalogue
  if (!model) return false
  const cur = Number(item.base_price) || 0
  if (cur <= 0) return false
  const db = dbPriceOf(item)
  if (db == null) return true
  return Math.abs(cur - db) > 0.01
}

export function isNewPart(item: {
  base_price?: number | string | null
  db_price?: unknown
}): boolean {
  return dbPriceOf(item) == null && (Number(item.base_price) || 0) > 0
}

export function matchClass(s: string): string {
  if (s.includes('一致') || s.includes('已同步')) return 'ok'
  if (s.includes('差异') || s.includes('待填') || s.includes('缺失')) return 'warn'
  if (s.includes('新部件') || s.includes('跨币种')) return 'new'
  return ''
}

export function computeKpMatch(item: {
  db_price?: unknown
  base_price?: number | string | null
  currency?: string | null
  db_currency?: string | null
  match_status?: string
}): void {
  const db = dbPriceOf(item)
  const cur = Number(item.base_price) || 0
  if (db == null) {
    item.match_status = cur > 0 ? '🆕 新部件' : '❌ 缺失 (请填写)'
    return
  }
  const itemCur = item.currency || 'RMB'
  const dbCur = item.db_currency || 'RMB'
  if (itemCur !== dbCur) {
    item.match_status = `💱 跨币种 (本行 ${itemCur} / 库 ${dbCur})`
    return
  }
  if (cur === 0) {
    item.match_status = `⚠️ 待填入 [DB=${db}]`
  } else if (Math.abs(cur - db) > 0.01) {
    item.match_status = `⚠️ 差异 (当前: ${cur}, DB: ${db})`
  } else {
    item.match_status = `✅ 一致 [DB=${db}]`
  }
}
