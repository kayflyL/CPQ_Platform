/**
 * 策略中心 API（对接 /api/strategies）。
 * domain: requirement/selection/pricing/market；status: draft/testing/active/archived
 */
import axios from 'axios'
import type { PolicyDocBody } from '@/constants/policyMeta'

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
  // 策略文档库便捷方法(domain=policy, type=document)
  listDocs: (status?: StrategyStatus) =>
    RESP<{ strategies: Strategy[] }>(axios.get('/api/strategies/', { params: { domain: 'policy', status } })),
  saveDoc: (data: { id?: number; name: string; body: PolicyDocBody; description?: string; change_reason?: string; status?: StrategyStatus }) =>
    data.id
      ? RESP<Strategy>(axios.put(`/api/strategies/${data.id}`, {
          name: data.name, body: data.body, description: data.description,
          change_reason: data.change_reason, status: data.status,
        }))
      : RESP<Strategy>(axios.post('/api/strategies/', {
          domain: 'policy', type: 'document', name: data.name, body: data.body,
          description: data.description, change_reason: data.change_reason, status: data.status || 'active',
        })),
}
