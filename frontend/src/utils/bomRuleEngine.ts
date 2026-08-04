/** BOM 模板规则求值器 — 按 row.rule 算每行 desc/qty。
 * 规则跟模板一起存 JSONB;求值跑前端(所见即所得,bomContext 不持久化)。
 * 失败语义:算不出(变量缺失/part 不存在)→ fallback;manual → 留空手填(不走 fallback)。 */
import type { BomTemplateRow, DescSource, QtySource, BomRule } from '@/api/serverConfig'

const SHORT_LABEL: Record<string, string> = {
  x16: 'X16', x8: 'X8', nvme: 'NVMe', sata: 'SATA', ocp_x8: 'OCP', ocp_x16: 'OCP', blank: '',
}
const DRIVE_KINDS = ['SATA', 'SAS', 'NVMe'] as const

export interface BomEvalContext {
  vars: Record<string, any>          // ${var} 插值 + config_value/config_calc 取值
  parts: any[]                        // baseConfig.parts(含 effectiveBaseParts 替换的背板行)
  rear: Record<string, string[]>      // IO1-4 + OCP → option_type[]
  frontCableQty: (k: string) => number
  frontCableInfo: (k: string) => { pn: string; n: number; group: number | '-'; price: number; name: string }
}

// 中英品类对照：模板 row 常填英文 category，baseline 底盘件 category 多为中文（parts_master）。
// 不加这个，part_field kind 的 heatsink/rail/cable 行因中英不匹配取不到底盘件 → 显示空。
const CATEGORY_CN_EN: Record<string, string[]> = {
  heatsink: ['散热器', '散热'],
  fan: ['风扇'],
  rail: ['滑轨', '导轨'],
  chassis: ['机箱'],
  backplane: ['背板'],
  cable: ['线缆'],
}
// 宽松 category 匹配(与 L6ChassisConfig.partByCategory 一致,零破坏)
function findPart(parts: any[], cat: string): any | null {
  const cl = cat.toLowerCase()
  const aliases = CATEGORY_CN_EN[cl] || []
  return parts.find((p: any) => {
    const c = (p.category || '').toLowerCase()
    const n = (p.name || '').toLowerCase()
    return c === cl || c.includes(cl) || n.includes(cl)
      || aliases.some(a => c.includes(a) || n.includes(a))
      || (cat === 'rail' && (n.includes('rail') || n.includes('slide')))
  }) || null
}

function readField(part: any, field: string): any {
  if (!part) return undefined
  if (field.startsWith('specs.')) return (part.specs as any)?.[field.slice(6)]
  return (part as any)[field]
}

// I6 R25 + R27：机型标准 riser——数据驱动（{slot:desc} 按槽位、键大小写不敏感，或字符串），
// 未配置返回 undefined（留空手填，拒绝硬编码）
function stdRiserFor(std: any, slot: string): string | undefined {
  if (std && typeof std === 'object') {
    if (std[slot]) return std[slot]
    const k = Object.keys(std).find((x) => x.toLowerCase() === slot)
    return (k && std[k]) || std.default
  }
  return std || undefined
}

// ${var} 插值;任一变量缺失/空 → null(整串失败走 fallback)
function renderTpl(tpl: string, vars: Record<string, any>): string | null {
  let missing = false
  const out = tpl.replace(/\$\{(\w+)\}/g, (_, k) => {
    const v = vars[k]
    if (v == null || v === '') { missing = true; return '' }
    return String(v)
  })
  return missing ? null : out
}

function structCount(scope: string, ctx: BomEvalContext, row: BomTemplateRow): string {
  if (scope === 'io_slot') {
    // I6 R25 + R26 + R27：riser 规格全数据驱动（standard_riser 默认 / riser_x16 升级），不硬编码。
    // 装 GPU → 全槽 riser_x16；高带宽网卡(100G+) → IO1 riser_x16；否则按槽位 standard_riser；无数据留空。
    const gpuQty = ctx.vars.gpu_qty || 0
    const slot = String(row.slot || '').toLowerCase()
    const x16 = ctx.vars.riser_x16
    if (gpuQty > 0) return x16 || ''
    if (ctx.vars.high_bw_nic && slot === 'io1') return x16 || ''
    return stdRiserFor(ctx.vars.standard_riser, slot) || ''
  }
  if (scope === 'rear_all') {
    const all: Record<string, number> = {}
    for (const slot of Object.keys(ctx.rear)) {
      for (const t of (ctx.rear[slot] || [])) if (t !== 'blank') all[t] = (all[t] || 0) + 1
    }
    const parts: string[] = []
    const gpuQty = ctx.vars.gpu_qty || 0
    if (gpuQty > 0) parts.push(`${gpuQty}*GPU`)
    for (const [t, n] of Object.entries(all)) parts.push(`${n}*${SHORT_LABEL[t] || t}`)
    // 直连机型：NVMe 盘直连 CPU，Direct connected 汇总追加 "N NVME"（盘数驱动，见 ESA24V3-P 典型配置）
    const nvmeQty = ctx.vars.nvme_count || 0
    if (nvmeQty > 0) parts.push(`${nvmeQty}NVME`)
    return parts.join('+')
  }
  if (scope === 'gpu_direct') {
    // GPU 直连汇总（模板 1 的 rear_summary「GPU 直连」行用）：只输出 GPU 数量。
    // 严格"配了 GPU 才显示"：不配 GPU → 空串，与 qty(config_calc gpu_qty) 同空 → BomTable 整行隐藏。
    const gpuQty = ctx.vars.gpu_qty || 0
    return gpuQty > 0 ? `${gpuQty}*GPU` : ''
  }
  if (scope === 'front_cables') {
    const cables = DRIVE_KINDS.map(k => {
      const q = ctx.frontCableQty(k); const info = ctx.frontCableInfo(k)
      if (q <= 0) return null
      return `${q}*${info.pn || k}`
    }).filter(Boolean)
    return cables.join('，')
  }
  return ''
}

// 返回 null = 算不出(外层决定是否走 fallback)
function tryDesc(src: DescSource, ctx: BomEvalContext, row: BomTemplateRow): string | null {
  switch (src.kind) {
    case 'fixed': return src.value || null
    case 'manual': return null
    case 'part_field': {
      const v = readField(findPart(ctx.parts, src.category), src.field)
      return (v != null && v !== '') ? String(v) : null
    }
    case 'template': return renderTpl(src.template, ctx.vars)
    case 'struct_count': { const s = structCount(src.scope, ctx, row); return s || null }
    case 'config_value': { const v = ctx.vars[src.key]; return (v != null && v !== '') ? String(v) : null }
  }
}

function tryQty(src: QtySource, ctx: BomEvalContext): number | null {
  switch (src.kind) {
    case 'fixed': return src.value           // fixed 即便 0 也算有效
    case 'manual': return null
    case 'part_quantity': {
      const p = findPart(ctx.parts, src.category)
      const q: any = (p as any)?.quantity
      return (q != null && q !== '' && Number(q) > 0) ? Number(q) : null
    }
    case 'config_calc': {
      const v = ctx.vars[src.key]; const n = Number(v)
      return (v != null && n > 0) ? n : null
    }
  }
}

function evalDesc(rule: BomRule | undefined, ctx: BomEvalContext, row: BomTemplateRow): string {
  if (!rule) return ''
  const v = tryDesc(rule.desc, ctx, row)
  if (v != null) return v
  if (rule.desc.kind === 'manual') return ''        // manual 不走 fallback
  if (rule.desc_fallback) return tryDesc(rule.desc_fallback, ctx, row) ?? ''
  return ''
}

function evalQty(rule: BomRule | undefined, ctx: BomEvalContext): number | string {
  if (!rule) return ''
  const v = tryQty(rule.qty, ctx)
  if (v != null) return v
  if (rule.qty.kind === 'manual') return ''
  // 兼容 qty_fallback 在 rule 顶层或 rule.qty 内层两种写法（模板 fan 行曾把 fallback 嵌进 qty）
  const fb = rule.qty_fallback ?? (rule.qty as any)?.qty_fallback
  if (fb) return tryQty(fb, ctx) ?? ''
  return ''
}

/** 按 bom_template.rows + rule 求值 → Record<key,{desc,qty}>。
 * key = row.slot || row.type(与 BomTable 渲染对齐)。 */
export function evalBomContext(
  rows: BomTemplateRow[],
  ctx: BomEvalContext,
): Record<string, { desc: string; qty: number | string }> {
  const out: Record<string, { desc: string; qty: number | string }> = {}
  for (const row of rows) {
    const key = row.slot || row.type
    out[key] = { desc: evalDesc(row.rule, ctx, row), qty: evalQty(row.rule, ctx) }
  }
  return out
}

export { SHORT_LABEL as BOM_SHORT_LABEL }
