/** BOM 模板求值器 — 按行类型统一规则算每行 desc/qty。
 * 设计（2026-09-15 定稿，三轮收敛）：模板 rows 存骨架（type/label/slot/mode）+
 * 可选 rule（逐行完整覆盖——用户从类型默认拷贝起步可改任何取值方式）。
 * 主语义 = 行类型默认（TYPE_RULES）；旧版「rule 必填预填 + 摘要常驻 + 四行展开编辑器」
 * 的呈现复杂度已拆掉，但逐行可配能力完整保留。
 * 求值跑前端(工作台/方案助手/模板预览所见即所得)；后端 bom_template_eval.py 同口径。
 * 失败语义:算不出(变量缺失/料件不存在)→ 规则兜底(类型默认的底盘件兜底数量跟形态走);
 * raid_slot 等手动行 → 留空，工作台手填（[[derive-must-have-manual-fallback]]）。 */
import type { BomTemplateRow, DescSource, QtySource, BomRule } from '@/api/serverConfig'

const SHORT_LABEL: Record<string, string> = {
  x16: 'X16', x8: 'X8', nvme: 'NVMe', sata: 'SATA', ocp_x8: 'OCP', ocp_x16: 'OCP', blank: '',
}

export interface BomEvalContext {
  vars: Record<string, any>          // ${var} 插值 + config_value/config_calc 取值
  parts: any[]                        // baseConfig.parts(含 effectiveBaseParts 替换的背板行)
  rear: Record<string, string[]>      // IO1-4 + OCP → option_type[]
  categoryAliases?: Record<string, string[]>

}

// ── 行类型 → 取值规则（唯一权威定义；后端 _TYPE_RULES 镜像同口径） ──
const pf = (category: string): DescSource => ({ kind: 'part_field', category, field: 'name' })
const pq = (category: string): QtySource => ({ kind: 'part_quantity', category })
const TYPE_RULES: Record<string, BomRule> = {
  front_backplane: { desc: { kind: 'template', template: '${bays}*3.5 ${bp_type_desc}' }, qty: { kind: 'fixed', value: 1 } },
  io_slot: { desc: { kind: 'struct_count', scope: 'io_slot' }, qty: { kind: 'fixed', value: 1 } },
  rear_summary: { desc: { kind: 'struct_count', scope: 'rear_all' }, qty: { kind: 'fixed', value: 1 } },
  heatsink: { desc: pf('heatsink'), qty: pq('heatsink'),
    desc_fallback: { kind: 'fixed', value: 'CPU 散热器' }, qty_fallback: { kind: 'fixed', value: 2 } },
  fan: { desc: pf('fan'), qty: pq('fan'), desc_fallback: { kind: 'fixed', value: '系统风扇' } },
  psu_requirement: { desc: { kind: 'template', template: '${psu_wattage}W' },
    desc_fallback: { kind: 'config_value', key: 'psu_name' }, qty: { kind: 'config_calc', key: 'psu_qty' } },
  gpu_power_cord: { desc: { kind: 'config_value', key: 'gpu_power_cord_desc' }, qty: { kind: 'config_calc', key: 'gpu_cable_qty' } },
  power_cord: { desc: { kind: 'fixed', value: '国标电源线' }, qty: { kind: 'config_calc', key: 'psu_qty' } },
  rail_kit: { desc: pf('rail'), qty: pq('rail'), qty_fallback: { kind: 'fixed', value: 1 } },
  raid_slot: { desc: { kind: 'manual' }, qty: { kind: 'manual' } },
}
// cable 行不走 TYPE_RULES（见 ruleForRow cable 分支）：单行汇总、qty 恒 1、描述按盘型分段（cableSegments）

/** Cable 行按盘型分组默认配置（用户定调 2026-09-17）：SATA/SAS 每 8 盘 1 组且文案带 RAID 型号前缀，
 *  NVMe 每 2 盘 1 组直接写。工厂函数防编辑页克隆时共享可变对象。 */
export function defaultCableKinds(): Record<string, { size: number; template: string }> {
  return {
    SATA: { size: 8, template: '${raid_model} SATA cable*${n}' },
    SAS: { size: 8, template: '${raid_model} SAS cable*${n}' },
    NVMe: { size: 2, template: 'NVMe cable*${n}' },
  }
}
const CABLE_KINDS = ['SATA', 'SAS', 'NVMe'] as const
/** Cable 行描述：按盘型分段——数量 = ⌈盘数/分组⌉，模板占位符 ${raid_model}（缺省去前缀）/${n}=组数/${count}=盘数。
 *  没盘的类型不出现；全没盘 → ''（整行隐藏，见 evalBomContext）。 */
export function cableSegments(
  kinds: Record<string, { size: number; template: string }> | undefined,
  vars: Record<string, any>,
): string {
  const conf = kinds || defaultCableKinds()
  const raid = String(vars.raid_model || '').trim()
  const seg: string[] = []
  for (const k of CABLE_KINDS) {
    const c = conf[k]
    if (!c) continue
    const count = Number(k === 'SATA' ? vars.sata_count : k === 'SAS' ? vars.sas_count : vars.nvme_count) || 0
    if (count <= 0) continue
    const n = Math.ceil(count / Math.max(1, Number(c.size) || 1))
    const line = String(c.template || '')
      .replace(/\$\{(\w+)\}/g, (_, key) =>
        key === 'n' ? String(n) : key === 'count' ? String(count) : key === 'raid_model' ? raid : '')
      .replace(/^\s+/, '')
    if (line) seg.push(line)
  }
  return seg.join('\n')
}

/** 行 → 规则。**逐行 rule 优先**：行上带完整 rule 就完全按它求值（用户在模板编辑页
 *  从类型默认拷贝改出的自定义）；省略 = 跟随类型默认——TYPE_RULES + 三个特殊分支：
 *  OCP 槽位行 qty 跟实际是否选了适配板走（未选 → 0 → 整行隐藏，防呆收在引擎层）；
 *  fan 兜底数量跟形态走（2U=6 / 4U=12，用户定调）；cable 单行汇总按盘型分段（用户定调
 *  2026-09-17：qty 恒 1，描述内写每类组数）。未知类型 → manual 留空手填。 */
export function ruleForRow(row: BomTemplateRow, form?: string): BomRule {
  if (row.rule) return row.rule
  const t = row.type
  if (t === 'io_slot' && String(row.slot || '').toUpperCase() === 'OCP')
    return { desc: { kind: 'struct_count', scope: 'io_slot' }, qty: { kind: 'config_calc', key: 'ocp_qty' } }
  if (t === 'fan') {
    return { ...TYPE_RULES.fan, qty_fallback: { kind: 'fixed', value: form === '4U' ? 12 : 6 } }
  }
  if (t === 'cable') {
    return { desc: { kind: 'cable_groups', kinds: defaultCableKinds() }, qty: { kind: 'fixed', value: 1 } }
  }
  return TYPE_RULES[t] || TYPE_RULES.raid_slot
}

/** 变量键 → 中文标签（编辑页「＋变量」下拉与取值来源选择用） */
export const VAR_ZH: Record<string, string> = {
  bays: '盘位数', form: '机箱形态', bp_type_desc: '背板类型',
  psu_qty: '电源数量', psu_wattage: '电源瓦数', psu_name: '电源名称',
  gpu_qty: 'GPU数量', gpu_cable_qty: 'GPU线缆数量', gpu_power_cord_desc: 'GPU电源线描述',
  nvme_count: 'NVMe盘数', raid_model: 'RAID型号', sata_count: 'SATA盘数', sas_count: 'SAS盘数', ocp_qty: 'OCP选配',
}

// 分级 category 匹配：①category 命中（精确/子串/别名）优先 ②找不到才退 name 子串。
// 别名来自调用方注入的 system_config.bom_category_aliases（拒绝前端硬编码中英词表）。
// 防「线缆蹭类」：基准配置挂的「风扇背板转接线」（name 含"风扇"）不得抢先于「机箱风扇」类真件。
export function findBomPart(parts: any[], cat: string, categoryAliases?: Record<string, string[]>): any | null {
  const cl = cat.toLowerCase()
  const aliasList = (categoryAliases || {})[cl] || []
  const catHit = (p: any) => {
    const c = (p.category || '').toLowerCase()
    return c === cl || c.includes(cl) || aliasList.some(a => c.includes(a))
  }
  const nameHit = (p: any) => {
    const n = (p.name || '').toLowerCase()
    return n.includes(cl) || aliasList.some(a => n.includes(a))
  }
  return parts.find(catHit) || parts.find(nameHit) || null
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

/** 后面板实际选卡（option_type 数组，重复=数量）→ 槽位规格签名（如 "3*X16+1*X8"）。
 * 口径与后端 bom_compare._riser_signature 一致（宽度倒序、忽略形态词 FHFL/FHHL）。 */
function rearSpecSignature(picked: string[]): string {
  const agg: Record<string, number> = {}
  for (const t of picked) {
    const label = SHORT_LABEL[t]
    if (!label) continue
    agg[label] = (agg[label] || 0) + 1
  }
  const order: Record<string, number> = { X16: 0, X8: 1, NVMe: 2, SATA: 3 }
  return Object.keys(agg)
    .sort((a, b) => (order[a] ?? 99) - (order[b] ?? 99) || a.localeCompare(b))
    .map((k) => `${agg[k]}*${k}`)
    .join('+')
}

function structCount(scope: string, ctx: BomEvalContext, row: BomTemplateRow): string {
  if (scope === 'io_slot') {
    // I6 R25 + R26 + R27 + R28：riser 规格全数据驱动（standard_riser 默认 / riser_x16 升级），不硬编码。
    // 装 GPU → 全槽 riser_x16；高带宽网卡(100G+) → IO1 riser_x16（硬约束优先）；
    // 后面板显式选卡（重复=数量）→ 按实际选择输出规格签名（如 "3*X16+1*X8"）；否则按槽位 standard_riser；无数据留空。
    const gpuQty = ctx.vars.gpu_qty || 0
    const slot = String(row.slot || '').toLowerCase()
    const x16 = ctx.vars.riser_x16
    // OCP 网络槽（独立分段，不占 PCIe）：desc 跟实际选的适配板（ocp_x8/ocp_x16）走；
    // 未选 → 空串，配合 qty ocp_qty=0 → 整行隐藏（BomTable / 规格书空行过滤一致）
    if (slot === 'ocp') {
      const t = (ctx.rear['OCP'] || []).find((x) => x !== 'blank')
      if (t === 'ocp_x16') return 'OCP 3.0 X16'
      if (t === 'ocp_x8') return 'OCP 3.0 X8'
      return ''
    }
    if (gpuQty > 0) return x16 || ''
    if (ctx.vars.high_bw_nic && slot === 'io1') return x16 || ''
    // rear 键名是模板槽名（IO1/OCP 大写），slot 已转小写 → 大小写不敏感查找
    const rearKey = Object.keys(ctx.rear || {}).find((k) => k.toLowerCase() === slot)
    const picked = ((rearKey && ctx.rear[rearKey]) || []).filter((t) => t !== 'blank')
    if (picked.length) return rearSpecSignature(picked)
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
    // 直连机型：NVMe 盘直连 CPU，Direct connected 汇总追加 "N NVME"（盘数驱动，见 ESA240 V3 典型配置）
    const nvmeQty = ctx.vars.nvme_count || 0
    if (nvmeQty > 0) parts.push(`${nvmeQty}NVME`)
    return parts.join('+')
  }
  return ''
}

// 返回 null = 算不出(外层决定是否走 fallback)
function tryDesc(src: DescSource, ctx: BomEvalContext, row: BomTemplateRow): string | null {
  switch (src.kind) {
    case 'fixed': return src.value || null
    case 'manual': return null
    case 'part_field': {
      const v = readField(findBomPart(ctx.parts, src.category, ctx.categoryAliases), src.field)
      return (v != null && v !== '') ? String(v) : null
    }
    case 'template': return renderTpl(src.template, ctx.vars)
    case 'struct_count': { const s = structCount(src.scope, ctx, row); return s || null }
    case 'config_value': { const v = ctx.vars[src.key]; return (v != null && v !== '') ? String(v) : null }
    case 'cable_groups': { const s = cableSegments(src.kinds, ctx.vars); return s || null }
  }
}

function tryQty(src: QtySource, ctx: BomEvalContext): number | null {
  switch (src.kind) {
    case 'fixed': return src.value           // fixed 即便 0 也算有效
    case 'manual': return null
    case 'part_quantity': {
      const p = findBomPart(ctx.parts, src.category, ctx.categoryAliases)
      const q: any = (p as any)?.quantity
      return (q != null && q !== '' && Number(q) > 0) ? Number(q) : null
    }
    case 'config_calc': {
      const v = ctx.vars[src.key]; const n = Number(v)
      return (v != null && n > 0) ? n : null
    }
  }
}

export type EvalSrc = 'hit' | 'fb' | 'empty'

function evalDesc(rule: BomRule | undefined, ctx: BomEvalContext, row: BomTemplateRow): { v: string; src: EvalSrc } {
  if (!rule) return { v: '', src: 'empty' }
  const v = tryDesc(rule.desc, ctx, row)
  if (v != null) return { v, src: 'hit' }
  if (rule.desc.kind === 'manual') return { v: '', src: 'empty' }   // manual 不走 fallback
  if (rule.desc_fallback) {
    const f = tryDesc(rule.desc_fallback, ctx, row)
    return { v: f ?? '', src: f != null ? 'fb' : 'empty' }
  }
  return { v: '', src: 'empty' }
}

function evalQty(rule: BomRule | undefined, ctx: BomEvalContext): { v: number | string; src: EvalSrc } {
  if (!rule) return { v: '', src: 'empty' }
  const v = tryQty(rule.qty, ctx)
  if (v != null) return { v, src: 'hit' }
  if (rule.qty.kind === 'manual') return { v: '', src: 'empty' }
  if (rule.qty_fallback) {
    const f = tryQty(rule.qty_fallback, ctx)
    return { v: f ?? '', src: f != null ? 'fb' : 'empty' }
  }
  return { v: '', src: 'empty' }
}

/** 按 bom_template.rows（骨架）+ 行类型规则求值 → Record<key,{desc,qty,descSrc,qtySrc}>。
 * key = row.slot || row.type(与 BomTable 渲染对齐)；src = 取值来源（hit 主规则/fb 兜底/empty 空），
 * 供模板预览「所见即所算」标注，BomTable 等消费方只读 desc/qty 不受影响。
 * cable 行：qty 恒 1，但没盘（描述空）时连 qty 一起清空 → 整行隐藏。 */
export function evalBomContext(
  rows: BomTemplateRow[],
  ctx: BomEvalContext,
): Record<string, { desc: string; qty: number | string; descSrc: EvalSrc; qtySrc: EvalSrc }> {
  const out: Record<string, { desc: string; qty: number | string; descSrc: EvalSrc; qtySrc: EvalSrc }> = {}
  for (const row of rows) {
    const key = row.slot || row.type
    const rule = ruleForRow(row, ctx.vars.form)
    const d = evalDesc(rule, ctx, row)
    const q = row.type === 'cable' && !d.v
      ? { v: '' as const, src: 'empty' as EvalSrc }
      : evalQty(rule, ctx)
    out[key] = { desc: d.v, qty: q.v, descSrc: d.src, qtySrc: q.src }
  }
  return out
}

export { SHORT_LABEL as BOM_SHORT_LABEL }
