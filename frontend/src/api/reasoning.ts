/**
 * Requirement intelligence API — 商机详情页「生成报价」推理流客户端.
 * POST /api/reasoning/{oid}/generate 触发后台 pipeline；WS /api/reasoning/ws/{oid} 接收步骤流。
 */
import axios from 'axios'

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
  /** 预算校验标注（budget_check 节点注入；null/undefined=未超预算） */
  over_budget?: { amount: number; ratio: number } | null
  /** 预算利用不足标注（方案价/预算 < 阈值，默认 0.5；null=无） */
  underspend?: { ratio: number; amount: number } | null
  /** AI 校对结论（review 节点注入，阻塞式：通过/不通过 + 必改项） */
  audit?: { status: 'ok' | 'blocked'; issues: string[]; issue_count: number; checked_at?: string } | null
}

export interface GenerateOpts {
  supplement_text?: string        // 反答回填文本（后端拼到原需求后重跑）
  explicit_budget?: number        // 用户明确给预算
  force_complete?: boolean        // 跳过反问，强制走选型
  confirm?: Record<string, string> // LLM 确认面板决策 {item_id: accept|ignore}
}

export const reasoningApi = {
  /** 触发推理 pipeline（后台异步跑，步骤经 WS 推送）。重跑时传 supplement_text / confirm 决策 */
  generate: (opportunityId: string, requirementText: string, opts?: GenerateOpts) =>
    axios.post(`/api/reasoning/${encodeURIComponent(opportunityId)}/generate`, {
      requirement_text: requirementText,
      supplement_text: opts?.supplement_text,
      explicit_budget: opts?.explicit_budget,
      force_complete: opts?.force_complete ?? false,
      confirm: opts?.confirm ?? undefined,
    }),
  /** LLM 确认面板反馈（全部采纳/部分忽略）→ requirement_samples，不重跑 pipeline */
  confirmFeedback: (opportunityId: string, requirementText: string, decisions: Record<string, string>) =>
    axios.post(`/api/reasoning/${encodeURIComponent(opportunityId)}/confirm`, {
      requirement_text: requirementText,
      decisions,
    }),
}

/** WS 订阅某商机的推理步骤流（step_start/step_done/candidates_ready/pipeline_done/error） */
export function reasoningWsUrl(opportunityId: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/api/reasoning/ws/${encodeURIComponent(opportunityId)}`
}
