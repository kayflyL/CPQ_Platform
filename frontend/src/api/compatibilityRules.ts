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
  category?: string | null          // 业务分类（用户可自定义的开放标签，引擎不感知、仅组织用）
  /** 显式绑定的区域大类 id 列表（料号库大类；字段推断仅作建议） */
  regions?: string[]
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

/** 规则层组内规则行（archived 仅供灰显，不可勾） */
export interface KnowledgeRuleMeta {
  id: number
  name: string
  status: string
}

/** 规则层绑定面板的组元数据（规则明细 + 活跃计数 + 用法行） */
export interface KnowledgeGroupMeta {
  name: string
  usage: string
  count: number
  rules: KnowledgeRuleMeta[]
}

/** 单节点绑定：组绑定 ∪ 单条勾选 */
export interface NodeKnowledgeBinding {
  groups: string[]
  rule_ids: number[]
}

export const knowledgeApi = {
  /** 全量知识绑定 + 组清单（编辑入口=推理流画布·节点抽屉·规则层） */
  getBindings: () =>
    RESP<{ bindings: Record<string, NodeKnowledgeBinding>; groups: KnowledgeGroupMeta[] }>(
      axios.get('/api/compatibility-rules/knowledge/bindings')),
  /** 写单节点绑定：组与单条皆空 = 该节点解绑，其他节点不动 */
  setNodeBindings: (nodeKey: string, groups: string[], ruleIds: number[]) =>
    RESP<{ bindings: Record<string, NodeKnowledgeBinding> }>(
      axios.put('/api/compatibility-rules/knowledge/bindings',
        { node_key: nodeKey, groups, rule_ids: ruleIds })),
}

export const compatibilityRulesApi = {
  list: (params?: { type?: RuleType; status?: RuleStatus; category?: string; domain?: string }) =>
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
  recordHit: (id: number) =>
    RESP<{ id: number; hit_count: number; last_hit_at: string }>(axios.post(`/api/compatibility-rules/${id}/hit`)),
  stats: (id: number) =>
    RESP<{ hit_count: number; last_hit_at: string | null }>(axios.get(`/api/compatibility-rules/${id}/stats`)),
}
