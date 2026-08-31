/**
 * 需求分析规则库 API（/api/requirement-rules）。
 * 规则类型：clarity（明确度判定）/ budget（预算映射）。
 * 旧 rebuttal/workload（臆造选项反问）已随目录驱动引导上线删除。
 * 独立建表，运行中积累命中，为未来 LLM 喂语料。
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type RuleType =
  | 'clarity'
  | 'budget'
  | 'cpu_mem_generation'
  | 'category_alias'
  | 'type_package'
  | 'spec_rule'
  | 'capacity_match'
  | 'fallback_order'
  | 'check_rule'
  | 'platform_series_map'
  | 'raid_level_map'
  | 'type_alias'
  | 'cpu_vendor_map'
  | 'workload_map'
  | 'compliance_map'
  | 'gpu_form_map'
  | 'model_action_phrases'
  | 'kp_action_phrases'
  | 'gpu_brand_map'
  | 'spec_unit_patterns'
  | 'power_calibration'
  | 'capability_declaration'
export type RuleStatus = 'draft' | 'testing' | 'active' | 'archived'

export const RULE_TYPE_OPTIONS: Array<{ value: RuleType; label: string }> = [
  { value: 'clarity', label: '明确度判定' },
  { value: 'budget', label: '预算映射' },
  { value: 'cpu_mem_generation', label: 'CPU→内存代际' },
  { value: 'category_alias', label: '品类别名' },
  { value: 'type_package', label: '机型类型套餐' },
  { value: 'spec_rule', label: '规格匹配' },
  { value: 'capacity_match', label: '容量匹配' },
  { value: 'fallback_order', label: '选型放宽' },
  { value: 'check_rule', label: '方案检查' },
  { value: 'platform_series_map', label: '平台系列映射' },
  { value: 'raid_level_map', label: 'RAID 级别映射' },
  { value: 'type_alias', label: '类型别名' },
  { value: 'cpu_vendor_map', label: 'CPU 厂商映射' },
  { value: 'workload_map', label: '工作负载映射' },
  { value: 'compliance_map', label: '合规映射' },
  { value: 'gpu_form_map', label: 'GPU 形态映射' },
  { value: 'model_action_phrases', label: '机型意图词' },
  { value: 'kp_action_phrases', label: '配件意图词' },
  { value: 'gpu_brand_map', label: 'GPU 品牌词表' },
  { value: 'spec_unit_patterns', label: '规格单位正则' },
  { value: 'power_calibration', label: '功耗/电源校准' },
  { value: 'capability_declaration', label: '能力声明拦截' },
]

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
