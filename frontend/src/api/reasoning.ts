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
  /** 预算校验标注（budget_check 节点注入；null/undefined=未超预算） */
  over_budget?: { amount: number; ratio: number } | null
  /** 预算利用不足标注（方案价/预算 < 阈值，默认 0.5；null=无） */
  underspend?: { ratio: number; amount: number } | null
}

export interface GenerateOpts {
  supplement_text?: string        // 反答回填文本（后端拼到原需求后重跑）
  explicit_budget?: number        // 用户明确给预算
  force_complete?: boolean        // 跳过反问，强制走选型
}

export const reasoningApi = {
  /** 触发推理 pipeline（后台异步跑，步骤经 WS 推送）。重跑时传 supplement_text */
  generate: (opportunityId: string, requirementText: string, opts?: GenerateOpts) =>
    axios.post(`/api/reasoning/${encodeURIComponent(opportunityId)}/generate`, {
      requirement_text: requirementText,
      supplement_text: opts?.supplement_text,
      explicit_budget: opts?.explicit_budget,
      force_complete: opts?.force_complete ?? false,
    }),
}

/** WS 订阅某商机的推理步骤流（step_start/step_done/candidates_ready/pipeline_done/error） */
export function reasoningWsUrl(opportunityId: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/api/reasoning/ws/${encodeURIComponent(opportunityId)}`
}
