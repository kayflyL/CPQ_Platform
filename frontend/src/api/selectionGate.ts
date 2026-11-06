/**
 * 选型配置引擎 resolve API（/api/selection-gate，匿名只读、零价格）。
 * 唯一判定出口：报价工作台/机箱弹窗/公开向导全部消费同一端点，
 * 前端不再本地求值规则（selectionEngine.ts 求值已退役，仅存展示格式化）。
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface GateBlocked { id: number | null; model: string; reasons: Array<{ ruleId: number | null; ruleName: string; desc: string }> }
export interface GateOptions { allowed: Array<{ id: number | null; model: string; brand: string; specs: Record<string, any> }>; blocked: GateBlocked[] }
export interface GateViolation {
  ruleId: number | null
  ruleName: string
  action: string          // require/exclude/clamp
  severity: string        // conflict/require
  desc: string
  target?: string
  offenders?: string[]
  caused_by?: string[]
}
export interface GateAction { ruleId: number | null; ruleName: string; action: string; severity?: string; desc: string; target?: string; offenders?: string[]; assignField?: string; assignValue?: any; deriveTarget?: string; deriveQty?: number; derivePer?: number }
export interface GateBudget {
  psu_load_w: number | null
  psu_capacity_w: number | null
  slots: Record<string, { used: number; max: number | null }>
}

export interface ResolveResult {
  options: Record<string, GateOptions>
  violations: GateViolation[]
  derived: GateAction[]
  recommends: GateAction[]
  budget: GateBudget
  model_warnings?: Array<{ reason_code: string; message: string }>
  trace?: unknown
}

export interface GatePartInput {
  category: string
  pn?: string
  name?: string
  qty?: number
  id?: number | null
  specs?: Record<string, any>
}

export const selectionGateApi = {
  /** resolve 协议：入参 {base_config_id, parts, options?, trace?}；出参 ResolveResult */
  resolve: (payload: { base_config_id?: number | null; parts: GatePartInput[]; options?: boolean; trace?: boolean }) =>
    RESP<ResolveResult>(axios.post('/api/selection-gate/resolve', payload)),
}
