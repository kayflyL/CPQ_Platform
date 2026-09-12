/**
 * 推理流可视化配置 API（/api/reasoning-flow）。
 * 推理流 DAG：Skill 工作流节点与参数配置。
 * 改节点 config 立即生效（下次推理用新参数）；三层兜底在 run_pipeline（DB 异常回退模块常量）。
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type ReasoningNodeKey = 'input' | 'agent_fill' | 'model_reason' | 'kp_reason' | 'compose' | 'output' | 'agent' | 'condition'

export interface ReasoningNodeMeta {
  id: string
  type: string
  label: string
  runtime?: string | null
  position?: { x: number; y: number }
}
export interface ReasoningGraph {
  nodes: ReasoningNodeMeta[]
  edges: Array<{
    id?: string
    source: string
    target: string
    source_handle?: string | null
    target_handle?: string | null
  }>
}

export interface ReasoningFlow {
  id: number
  name: string
  version: number
  status: string
  graph: ReasoningGraph
  is_active: boolean
  description: string | null
  node_configs?: Partial<Record<ReasoningNodeKey, Record<string, any>>>  // 仅 get_active 返回
}

export const reasoningFlowApi = {
  get: (skillKey?: string) =>
    RESP<{ flow: ReasoningFlow | null }>(axios.get('/api/reasoning-flow/', {
      params: skillKey ? { skill_key: skillKey } : undefined,
    })),
  listVersions: (skillKey?: string) =>
    RESP<{ versions: ReasoningFlow[] }>(axios.get('/api/reasoning-flow/versions', {
      params: skillKey ? { skill_key: skillKey } : undefined,
    })),
  updateGraph: (graph: ReasoningGraph, skillKey?: string) =>
    RESP<ReasoningFlow>(axios.put('/api/reasoning-flow/graph', { graph }, {
      params: skillKey ? { skill_key: skillKey } : undefined,
    })),
  updateNode: (nodeKey: ReasoningNodeKey, config: Record<string, any>, label?: string, skillKey?: string) =>
    RESP<any>(axios.put(`/api/reasoning-flow/nodes/${nodeKey}`, { config, label }, {
      params: skillKey ? { skill_key: skillKey } : undefined,
    })),
  activate: (flowId: number) =>
    RESP<ReasoningFlow>(axios.post(`/api/reasoning-flow/versions/${flowId}/activate`, {})),
  getManual: (skillKey?: string) =>
    RESP<{ rules: string; manual: string; version: number }>(axios.get('/api/reasoning-flow/manual', {
      params: { skill_key: skillKey || 'requirement_analysis' },
    })),
  saveManualRules: (rules: string, skillKey?: string) =>
    RESP<{ ok: boolean; rules: string }>(axios.put('/api/reasoning-flow/manual-rules', {
      rules, skill_key: skillKey || 'requirement_analysis',
    })),
}
