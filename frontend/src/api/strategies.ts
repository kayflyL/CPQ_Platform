/**
 * 策略中心 API（对接 /api/strategies）。
 * domain: requirement/selection/pricing/market；status: draft/testing/active/archived
 */
import axios from 'axios'
import type { PolicyDocBody, StrategyModule } from '@/constants/policyMeta'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type StrategyDomain = 'requirement' | 'selection' | 'pricing' | 'market' | 'policy'
export type StrategyStatus = 'draft' | 'testing' | 'active' | 'archived'

export interface Strategy {
  id: number
  domain: StrategyDomain
  type: string
  name: string
  scope: Record<string, any> | null
  body: Record<string, any> | null
  status: StrategyStatus
  version: number
  change_reason: string | null
  description: string | null
  created_at: string | null
  updated_at: string | null
  created_by: string
  updated_by: string
}


export const strategyApi = {
  list: (params?: { domain?: StrategyDomain; status?: StrategyStatus; type?: string }) =>
    RESP<{ strategies: Strategy[] }>(axios.get('/api/strategies/', { params })),
  get: (id: number) => RESP<Strategy>(axios.get(`/api/strategies/${id}`)),
  create: (data: Partial<Strategy> & { domain: StrategyDomain; type: string; name: string }) =>
    RESP<Strategy>(axios.post('/api/strategies/', data)),
  update: (id: number, data: Partial<Strategy>) =>
    RESP<Strategy>(axios.put(`/api/strategies/${id}`, data)),
  setStatus: (id: number, status: StrategyStatus) =>
    RESP<Strategy>(axios.post(`/api/strategies/${id}/status`, { status })),
  delete: (id: number) => RESP<{ success: boolean }>(axios.delete(`/api/strategies/${id}`)),
  recordUsage: (id: number, data: { version?: number; ref_type?: string; ref_id?: string }) =>
    RESP<{ id: number }>(axios.post(`/api/strategies/${id}/usage`, data)),
  usageStats: (id: number) =>
    RESP<{ count: number; last_ref: string | null }>(axios.get(`/api/strategies/${id}/usage`)),
}

/**
 * 策略文档库（/api/policy-docs）—— 无数字 id，增删改查用「创建时间戳 (module, created_at)」定位。
 * 文档独立存 rules.policy_docs 表（2026-08-04 起，不再与策略规则混表、不再有自增 id）。
 */
export interface PolicyDoc {
  name: string
  module: StrategyModule
  category: string
  sort_order: number
  content_markdown: string
  description: string | null
  status: StrategyStatus
  version: number
  created_at: string | null      // 定位键（创建时间戳，不可变）
  updated_at: string | null
  created_by: string
  updated_by: string
  body: PolicyDocBody            // 兼容旧 readDocBody
}

export const policyDocApi = {
  list: (module?: StrategyModule, status?: StrategyStatus) =>
    RESP<{ docs: PolicyDoc[] }>(axios.get('/api/policy-docs/', { params: { module, status } })),
  create: (data: {
    module: StrategyModule; name: string; category: string; sort_order: number;
    content_markdown: string; description?: string; status?: StrategyStatus;
  }) =>
    RESP<PolicyDoc>(axios.post('/api/policy-docs/', data)),
  update: (data: {
    module: StrategyModule; created_at: string; name?: string; category?: string;
    sort_order?: number; content_markdown?: string; description?: string; status?: StrategyStatus;
  }) =>
    RESP<PolicyDoc>(axios.put('/api/policy-docs/', data)),
  remove: (module: StrategyModule, created_at: string) =>
    RESP<{ success: boolean }>(axios.delete('/api/policy-docs/', { params: { module, created_at } })),
}
