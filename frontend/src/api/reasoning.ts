/**
 * 推理结果类型定义（方案 / 候选 / 告警），供试运行与产出物卡片复用。
 * 旧 /api/reasoning 商机推理流客户端已随 AI Office 整改移除。
 */

export type CandidateSource = 'l6' | 'kp' | 'baseline'

export interface Candidate {
  source: CandidateSource
  id: string
  pn?: string
  name?: string
  category?: string
  section?: string
  brand?: string
  unit_price?: number | null
  currency?: string
  specs?: Record<string, any>
  /** baseline 专属 */
  config_id?: number
  model?: string
  series?: string
  form?: string
  parts_count?: number
}

/** 整机方案（baseline 底盘 + 配齐 KP）—— 一张候选整机 BOM */
export interface PlanSummary {
  parts_count: number
  kp_count: number
  l6_cost?: number
  kp_cost?: number
  total_cost: number
}
export interface PlanCfg {
  bom_source: 'excel'
  bom_excel_rows: any[]
}

/** 选型配置规则在方案上的校验/推荐告警（需求分析 → 选型配置 打通后由后端 build_plan 注入） */
export interface SelectionAlert {
  ruleId: number | null
  ruleName: string
  action: 'require' | 'exclude' | 'recommend'
  severity: 'conflict' | 'require' | 'info'
  desc: string
  target?: string
  offenders?: string[]
}

/** 方案派生信号：需求分析执行选型配置规则后回填（背板类型 + 各类型线缆根数） */
export interface ChassisSignals {
  psu_wattage?: string
  bp_type?: 'tri' | 'dc'
  cable_qty_by_kind?: Partial<Record<'SATA' | 'SAS' | 'NVMe' | 'GPU线', number>>
}

export interface Plan {
  config_id: number
  server_model_id?: number | null
  name: string
  use?: string
  product_content?: Record<string, any> | null
  model: string
  series: string
  form: string
  bays?: number | null
  bom_template_id?: number | null
  summary: PlanSummary
  /** model_recommend 策略标注（recommend/avoid/neutral），仅标注不驱动检索 */
  recommend_level?: string
  selling_points?: string
  /** 喂给 BomTable 的 excel 快照（L6 行 category='L6' + KP 行 category='Key Parts'） */
  cfg: PlanCfg
  /** 选型配置规则派生信号（背板 tri/dc + 各类型线缆根数；规则在选型配置页管） */
  chassis_signals?: ChassisSignals
  /** 选型配置规则校验告警（require/exclude 冲突、recommend 推荐） */
  selection_alerts?: SelectionAlert[]
  /** BOM案例库在线防偏差告警（P2）：最相似案例规格对照，偏差提示；只提示不自动改方案 */
  experience_alerts?: Array<{ severity: 'error' | 'warning' | 'info'; desc: string }>
  /** 预算校验标注（null/undefined=未超预算） */
  over_budget?: { amount: number; ratio: number } | null
  /** 预算利用不足标注（方案价/预算 < 阈值，默认 0.5；null=无） */
  underspend?: { ratio: number; amount: number } | null
  /** AI 校对结论（阻塞式：通过/不通过 + 必改项） */
  audit?: { status: 'ok' | 'blocked'; issues: string[]; issue_count: number; checked_at?: string } | null
}
