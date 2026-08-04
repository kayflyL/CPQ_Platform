/**
 * usePlanBom — 把整机方案(Plan)转成 BomTable 可渲染的 live cfg（BOM 模板格式 L6）。
 *
 * Plan.cfg.bom_excel_rows 是 base_config_parts 的平铺；这里按 baseline 的 bom_template rows
 * 跑 bomRuleEngine 求值出 bom_context，让 BomTable live 模式按模板格式渲染 L6
 * （CPU/内存/机箱… 分组行），与工作台左栏一致。无模板/取失败时回落 excel 平铺。
 *
 * 上下文是 baseline-only 近似：parts 来自基准配置底盘件；vars 从 parts+plan 派生。
 * L6 描述式原则（R25）：io_slot riser 用机型标准（config_content.standard_riser）+ GPU 信号，
 * 不查后面板料号；rear（rearIOApi）仅服务 4U 模板 rear_all 汇总，frontCables 按 KP 盘型推导。
 * 让推理 BOM 的 IO/OCP/线缆行也能填出结构（与工作台选配器同源，默认值可后续调整）。
 */
import { bomTemplateApi, baseConfigApi, rearIOApi } from '@/api/serverConfig'
import { evalBomContext, type BomEvalContext } from '@/utils/bomRuleEngine'
import { rearSlotsFor, COMBO_REAR_SLOTS, rearIOBucket } from '@/constants/chassisMeta'
import { normalizeDriveKind } from '@/stores/selectionEngine'
import { DRIVE_RE, GPU_RE, PSU_RE, gpuModelFrom, raidModelFrom, cableDescFrom , highBwNicFrom } from '@/utils/bomL6Derive'
import type { Plan } from '@/api/reasoning'

/** 前面板线缆每组盘数（镜像 CRE 规则默认：SATA/SAS ÷8、NVMe ÷2；per 可在选型配置页改） */
const CABLE_PER: Record<string, number> = { SATA: 8, SAS: 8, NVMe: 2 }
/** 线缆类型遍历序（struct_count front_cables 的 DRIVE_KINDS 同序） */
const CABLE_KINDS = ['SATA', 'SAS', 'NVMe'] as const

/**
 * 方案侧某类型线缆根数：优先取后端 build_plan 应用选型配置规则后的派生信号
 * （cable_qty_by_kind，规则在选型配置页管 = 唯一真相源）；旧方案无信号回退硬编码镜像。
 */
function planCableQty(plan: Plan, kind: string, fallback: number): number {
  const m = plan.chassis_signals?.cable_qty_by_kind as Record<string, number> | undefined
  return m && kind in m ? Number(m[kind]) || 0 : fallback
}

function sumQty(parts: any[], re: RegExp): number {
  return parts
    .filter((p) => re.test(`${p.category || ''} ${p.part_category || ''} ${p.name || ''}`))
    .reduce((s, p) => s + (Number(p.quantity ?? p.qty) || 0), 0)
}

/** 盘类型数量统计（按 KP 件名称/描述嗅探，与 selectionEngine.normalizeDriveKind 同源） */
export function driveKindCounts(items: any[]): { sata: number; sas: number; nvme: number } {
  const out = { sata: 0, sas: 0, nvme: 0 }
  for (const it of items || []) {
    const kind = normalizeDriveKind(`${it.part_category || ''} ${it.catalogue || ''} ${it.description || ''}`)
    if (kind === 'SATA') out.sata += Number(it.qty) || 0
    else if (kind === 'SAS') out.sas += Number(it.qty) || 0
    else if (kind === 'NVMe') out.nvme += Number(it.qty) || 0
  }
  return out
}

/** 某类型前面板线缆根数（盘数 ÷ 每组盘数，向上取整；0 盘 = 0 根） */
export function frontCableQtyFor(kind: string, counts: { sata: number; sas: number; nvme: number }, gpuQty: number): number {
  if (kind === 'GPU线') return gpuQty || 0
  const n = kind === 'SATA' ? counts.sata : kind === 'SAS' ? counts.sas : kind === 'NVMe' ? counts.nvme : 0
  if (n <= 0) return 0
  return Math.ceil(n / (CABLE_PER[kind] || 1))
}

/** 后面板默认选配：组合槽(IO1/IO2)按 1×X16+1×X8、OCP 按 X8（料号库有则取）；其余槽默认挡片。 */
export function defaultRearFrom(
  slotDefs: { name: string; cap: number }[],
  options: Record<string, { option_type: string }[]>,
): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const s of slotDefs || []) {
    const opts = (options?.[s.name] || []).map((o) => o.option_type).filter((t) => t && t !== 'blank')
    if (!opts.length) continue
    if (s.name === 'OCP') {
      const t = opts.includes('ocp_x8') ? 'ocp_x8' : opts[0]
      out[s.name] = [t]
    } else if (COMBO_REAR_SLOTS.includes(s.name)) {
      const has16 = opts.includes('x16')
      const has8 = opts.includes('x8')
      out[s.name] = has16 && has8 ? ['x16', 'x8'] : [opts[0]]
    }
    // 其余槽（IO3/IO4…）：默认挡片，留给选配器/人工
  }
  return out
}

function deriveVars(parts: any[], items: any[], plan: Plan, base: any,
                    counts: { sata: number; sas: number; nvme: number }): Record<string, any> {
  // 背板类型：优先取后端选型规则派生的 bp_type（选型配置页规则 = 唯一真相源）；
  // 旧方案无信号才回退基准 bp_*_pn / 硬编码镜像（含 NVMe 盘 → tri，否则 dc）
  const bpType = plan.chassis_signals?.bp_type
    ?? (base?.bp_tri_pn ? 'tri' : base?.bp_dc_pn ? 'dc' : (counts.nvme > 0 ? 'tri' : 'dc'))
  // GPU/硬盘是 KP 件（不在底盘 parts 里），从 items 算；电源数优先取机箱 psu_bays
  const gpuQty = sumQty(items, GPU_RE)
  const gpuModel = gpuModelFrom(items)
  const raidModel = raidModelFrom(items)
  // I6 R25 + R27：L6 描述式——io_slot riser 数据驱动（standard_riser/riser_x16），不硬编码、不查料号
  const cc = ((base as any)?.config_content || {})
  const standardRiser = cc.standard_riser || ''
  const riserX16 = cc.riser_x16 || ''
  // R26：高带宽网卡（100G+，x16 卡）→ IO1 riser 升级 x16
  const highBwNic = highBwNicFrom(items)
  return {
    bays: plan.bays ?? '',
    form: plan.form || '',
    series: plan.series || '',
    standard_riser: standardRiser,
    riser_x16: riserX16,
    high_bw_nic: highBwNic,
    gpu_qty: gpuQty,
    drive_count: sumQty(items, DRIVE_RE),
    psu_qty: (plan as any).chassis_signals?.psu_qty ?? base?.psu_bays ?? sumQty(parts, PSU_RE),  // 需求显式 N* 1300W 优先
    psu_wattage: (plan as any).chassis_signals?.psu_wattage ?? '',  // 需求功率或 build_plan 按 GPU 推断
    bp_type: bpType,
    bp_type_desc: bpType === 'tri' ? 'NVMe/SATA/SAS' : 'SATA/SAS',
    gpu_cable_qty: planCableQty(plan, 'GPU线', gpuQty),  // 规则派生（默认每块 GPU 1 根）
    cable_qty: CABLE_KINDS.reduce((s, k) => s + planCableQty(plan, k, frontCableQtyFor(k, counts, gpuQty)), 0),
    // 目录化推导（desc 全部是描述，绝不显示 pn）：
    gpu_model: gpuModel,                                  // GPU 型号（去容量/后缀）
    nvme_count: counts.nvme,                              // NVMe 盘数（Direct connected / NVMe 缆用）
    gpu_power_cord_desc: gpuModel ? `${gpuModel} power cord` : '',  // GPU Power cord 行
    raid_model: raidModel,                                // RAID 型号（Cable 行用）
    cable_desc: cableDescFrom(counts, raidModel),         // Cable 行（多行，如 "9560 4SAS Cable\n2NVMe Cable"）
  }
}

/** Plan 的 KP 行 → 工作台 item 形状（category='Key Parts'） */
export function kpItemsFromPlan(plan: Plan): any[] {
  return (plan.cfg.bom_excel_rows || [])
    .filter((r: any) => r.category === 'Key Parts')
    .map((r: any) => ({
      category: 'Key Parts',
      catalogue: r.catalogue || '',
      pn: r.catalogue || '',
      part_category: r.part_category || '',
      description: r.description || '',
      qty: r.qty || 1,
      base_price: r.base_price || 0,
      profit_margin: 10,
      currency: r.currency || 'RMB',
    }))
}

export interface PlanLiveCfg {
  bom_source: 'live' | 'excel'
  bom_template?: { rows: any[] } | null
  bom_context?: Record<string, { desc: string; qty: number | string }>
  bom_excel_rows?: any[]
  items: any[]
}

/**
 * 构造 BomTable 可渲染的 cfg：有模板走 live（模板格式 L6），无模板/取失败回落 excel 平铺。
 * items 始终为 KP 行（live 模式 BomTable KP 区从 items 读）。
 */
export async function buildPlanCfg(plan: Plan): Promise<PlanLiveCfg> {
  const items = kpItemsFromPlan(plan)
  try {
    const [tpl, base] = await Promise.all([
      bomTemplateApi.getForBaseConfig(plan.config_id),
      baseConfigApi.get(plan.config_id),
    ])
    // 后面板选项取不到不致命：rear 留空（IO 行回落空），其余模板行照常渲染（不进 excel fallback）
    let rearRes: any = {}
    try {
      rearRes = await rearIOApi.getOptions(rearIOBucket(plan.series))
    } catch { /* ignore */ }
    const rows = (tpl as any)?.rows || []
    if (!rows.length) throw new Error('no bom_template rows')
    // 注入背板件（bp_tri_pn/bp_dc_pn → 背板行），对齐工作台 effectiveBaseParts：
    // base_config_parts 不含背板（PN 在 base_configs.bp_*_pn 字段），不注入则模板 part_field 背板行取不到
    const parts = [...((base as any)?.parts || [])]
    const bpPn = (base as any)?.bp_tri_pn || (base as any)?.bp_dc_pn
    if (bpPn && !parts.some((p: any) => (p.category || '').includes('背板'))) {
      parts.push({ category: '前置硬盘背板', name: bpPn, pn: bpPn, quantity: 1, specs: {} })
    }
    const counts = driveKindCounts(items)
    const gpuQty = sumQty(items, GPU_RE)
    // 后面板默认选配：槽位布局取 base_config.rear_slots（能力档案），缺失兜底按 form/series 标准布局
    const slotDefs = (base as any)?.rear_slots?.length ? (base as any).rear_slots : rearSlotsFor(plan.form, plan.series)
    const rear = defaultRearFrom(slotDefs, (rearRes as any)?.slots || {})
    const ctx: BomEvalContext = {
      vars: deriveVars(parts, items, plan, base, counts),
      parts,
      rear,
      frontCableQty: (k) => planCableQty(plan, k, frontCableQtyFor(k, counts, gpuQty)),
      frontCableInfo: (k) => {
        const n = planCableQty(plan, k, frontCableQtyFor(k, counts, gpuQty))
        return { pn: k, n, group: CABLE_PER[k] ?? ('-' as const), price: 0, name: '' }
      },
    }
    const bom_context = evalBomContext(rows, ctx)
    return { bom_source: 'live', bom_template: { rows }, bom_context, items }
  } catch {
    return { bom_source: 'excel', bom_excel_rows: plan.cfg.bom_excel_rows, items }
  }
}
