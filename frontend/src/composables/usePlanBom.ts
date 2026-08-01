/**
 * usePlanBom — 把整机方案(Plan)转成 BomTable 可渲染的 live cfg（BOM 模板格式 L6）。
 *
 * Plan.cfg.bom_excel_rows 是 base_config_parts 的平铺；这里按 baseline 的 bom_template rows
 * 跑 bomRuleEngine 求值出 bom_context，让 BomTable live 模式按模板格式渲染 L6
 * （CPU/内存/机箱… 分组行），与工作台左栏一致。无模板/取失败时回落 excel 平铺。
 *
 * 上下文是 baseline-only 近似：parts 来自基准配置底盘件；vars 从 parts+plan 派生；
 * rear/frontCables 只有选配器交互才有，baseline 没有 → 相关行回落空
 * （多数模板的主干行 CPU/内存/GPU/电源/机箱 是 part_field，仍能正常解析）。
 */
import { bomTemplateApi, baseConfigApi } from '@/api/serverConfig'
import { evalBomContext, type BomEvalContext } from '@/utils/bomRuleEngine'
import type { Plan } from '@/api/reasoning'

const DRIVE_RE = /hdd|ssd|nvme|sata|sas|硬盘|存储/i
const GPU_RE = /gpu|显卡|图形/i
const PSU_RE = /psu|电源|power/i

function sumQty(parts: any[], re: RegExp): number {
  return parts
    .filter((p) => re.test((p.category || '') + ' ' + (p.name || '')))
    .reduce((s, p) => s + (Number(p.quantity) || 0), 0)
}

function deriveVars(parts: any[], plan: Plan, base: any): Record<string, any> {
  // 背板类型从 base_config.bp_tri_pn/bp_dc_pn 推断（tri=三模支持 NVMe，dc=直连）
  const bpType = base?.bp_tri_pn ? 'tri' : base?.bp_dc_pn ? 'dc' : ''
  return {
    bays: plan.bays ?? '',
    form: plan.form || '',
    series: plan.series || '',
    gpu_qty: sumQty(parts, GPU_RE),
    drive_count: sumQty(parts, DRIVE_RE),
    psu_qty: sumQty(parts, PSU_RE),
    psu_wattage: (plan as any).chassis_signals?.psu_wattage ?? '',  // 需求里的电源功率（后端注入）
    bp_type: bpType,
    bp_type_desc: bpType === 'tri' ? 'NVMe/SATA/SAS' : bpType === 'dc' ? 'SATA/SAS' : '',
    gpu_cable_qty: 0,
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
    const rows = (tpl as any)?.rows || []
    if (!rows.length) throw new Error('no bom_template rows')
    // 注入背板件（bp_tri_pn/bp_dc_pn → 背板行），对齐工作台 effectiveBaseParts：
    // base_config_parts 不含背板（PN 在 base_configs.bp_*_pn 字段），不注入则模板 part_field 背板行取不到
    const parts = [...((base as any)?.parts || [])]
    const bpPn = (base as any)?.bp_tri_pn || (base as any)?.bp_dc_pn
    if (bpPn && !parts.some((p: any) => (p.category || '').includes('背板'))) {
      parts.push({ category: '前置硬盘背板', name: bpPn, pn: bpPn, quantity: 1, specs: {} })
    }
    const ctx: BomEvalContext = {
      vars: deriveVars(parts, plan, base),
      parts,
      rear: {},
      frontCableQty: () => 0,
      frontCableInfo: () => ({ pn: '', n: 0, group: '-' as const, price: 0, name: '' }),
    }
    const bom_context = evalBomContext(rows, ctx)
    return { bom_source: 'live', bom_template: { rows }, bom_context, items }
  } catch {
    return { bom_source: 'excel', bom_excel_rows: plan.cfg.bom_excel_rows, items }
  }
}
