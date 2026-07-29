/**
 * 需求分析规则库 API（/api/requirement-rules）。
 * 三类规则：clarity（明确度判定）/ rebuttal（反问话术）/ budget（预算映射）。
 * 独立建表，运行中积累命中，为未来 LLM 喂语料。
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type RuleType = 'clarity' | 'rebuttal' | 'budget'
export type RuleStatus = 'draft' | 'testing' | 'active' | 'archived'

export interface RequirementRule {
  id: number
  domain: string
  type: RuleType
  name: string
  scope: Record<string, any> | null
  body: Record<string, any> | null
  status: RuleStatus
  version: number
  hit_count: number
  last_hit_at: string | null
  description?: string | null
  change_reason?: string | null
}

export interface RequirementSample {
  id: number
  rule_id: number
  sample_text?: string | null
  expected_result?: Record<string, any> | null
  source: string
  tags?: string[] | null
  enabled: boolean
}

export const requirementRulesApi = {
  list: (params?: { type?: RuleType; status?: RuleStatus }) =>
    RESP<{ rules: RequirementRule[] }>(axios.get('/api/requirement-rules/', { params })),
  get: (id: number) => RESP<RequirementRule>(axios.get(`/api/requirement-rules/${id}`)),
  create: (data: Partial<RequirementRule> & { type: RuleType; name: string }) =>
    RESP<RequirementRule>(axios.post('/api/requirement-rules/', data)),
  update: (id: number, data: Partial<RequirementRule>) =>
    RESP<RequirementRule>(axios.put(`/api/requirement-rules/${id}`, data)),
  setStatus: (id: number, status: RuleStatus) =>
    RESP<RequirementRule>(axios.post(`/api/requirement-rules/${id}/status`, { status })),
  remove: (id: number) =>
    RESP<{ success: boolean }>(axios.delete(`/api/requirement-rules/${id}`)),
  reset: () =>
    RESP<{ reset: boolean; count: number }>(axios.post('/api/requirement-rules/reset')),
  recordHit: (id: number) =>
    RESP<{ id: number; hit_count: number; last_hit_at: string }>(axios.post(`/api/requirement-rules/${id}/hit`)),
  stats: (id: number) =>
    RESP<{ hit_count: number; last_hit_at: string | null }>(axios.get(`/api/requirement-rules/${id}/stats`)),
  listSamples: (ruleId: number) =>
    RESP<{ samples: RequirementSample[] }>(axios.get(`/api/requirement-rules/${ruleId}/samples`)),
  addSample: (ruleId: number, data: Partial<RequirementSample>) =>
    RESP<RequirementSample>(axios.post(`/api/requirement-rules/${ruleId}/samples`, data)),
}
