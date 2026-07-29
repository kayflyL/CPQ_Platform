/**
 * 兼容性规则引擎 API（/api/compatibility-rules）。
 * 声明式 WHEN(条件)→THEN(动作) 规则，跨 KP 配件库 / 料号库 / 基准机箱 / 商机维度求值。
 * type: require(必配) / exclude(互斥) / derive(派生) / filter(过滤) / recommend(推荐)
 * body: { when:{all/any:[{field,op,value}]}, then:{action,...}, desc }
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type RuleType = 'require' | 'exclude' | 'derive' | 'filter' | 'recommend'
export type RuleStatus = 'draft' | 'testing' | 'active' | 'archived'

export interface CompatibilityRule {
  id: number
  domain: string
  type: RuleType
  name: string
  scope: Record<string, any> | null
  body: Record<string, any> | null       // { when, then, desc }
  status: RuleStatus
  version: number
  hit_count: number
  last_hit_at: string | null
  description?: string | null
  change_reason?: string | null
}

export const compatibilityRulesApi = {
  list: (params?: { type?: RuleType; status?: RuleStatus }) =>
    RESP<{ rules: CompatibilityRule[] }>(axios.get('/api/compatibility-rules/', { params })),
  get: (id: number) => RESP<CompatibilityRule>(axios.get(`/api/compatibility-rules/${id}`)),
  create: (data: Partial<CompatibilityRule> & { type: RuleType; name: string }) =>
    RESP<CompatibilityRule>(axios.post('/api/compatibility-rules/', data)),
  update: (id: number, data: Partial<CompatibilityRule>) =>
    RESP<CompatibilityRule>(axios.put(`/api/compatibility-rules/${id}`, data)),
  setStatus: (id: number, status: RuleStatus) =>
    RESP<CompatibilityRule>(axios.post(`/api/compatibility-rules/${id}/status`, { status })),
  remove: (id: number) =>
    RESP<{ success: boolean }>(axios.delete(`/api/compatibility-rules/${id}`)),
  reset: () =>
    RESP<{ reset: boolean; count: number }>(axios.post('/api/compatibility-rules/reset')),
  recordHit: (id: number) =>
    RESP<{ id: number; hit_count: number; last_hit_at: string }>(axios.post(`/api/compatibility-rules/${id}/hit`)),
  stats: (id: number) =>
    RESP<{ hit_count: number; last_hit_at: string | null }>(axios.get(`/api/compatibility-rules/${id}/stats`)),
}
