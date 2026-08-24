/**
 * 推理流可视化配置 API（/api/reasoning-flow）。
 * 推理流 DAG：Skill 工作流节点与参数配置。
 * 改节点 config 立即生效（下次推理用新参数）；三层兜底在 run_pipeline（DB 异常回退模块常量）。
 */
import axios from 'axios'
import type { Plan } from '@/api/reasoning'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type ReasoningNodeKey = 'input' | 'agent_fill' | 'model_reason' | 'kp_reason' | 'compose' | 'output' | 'agent' | 'rule' | 'branch' | 'assemble' | 'orchestrator' | 'condition'

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

/** 试运行事件（按执行顺序：pipeline_start / step_start / step_done / candidates_ready / pipeline_done / need_input） */
export interface TestRunEvent {
  type: string
  step?: string
  label?: string
  payload?: any
  [k: string]: any
}
/** 试运行结果：每步事件 + ext/kp_by_model/plans 明细（全从 ctx 取） */
export interface TestRunResult {
  events: TestRunEvent[]
  ext: Record<string, any>
  kp_by_model: Record<string, any[]>
  plans: Plan[]
  awaiting_input: boolean
  error?: string
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
  testRun: (text: string, budget?: number, forceComplete?: boolean, skillKey?: string) =>
    RESP<TestRunResult>(axios.post('/api/reasoning-flow/test-run', {
      requirement_text: text,
      explicit_budget: budget,
      force_complete: forceComplete ?? true,
    }, { params: skillKey ? { skill_key: skillKey } : undefined })),
  /** 流式试运行：注册 run_id，事件经 WS /api/reasoning-flow/test-run-ws/{run_id} 实时推送 */
  testRunStart: (text: string, budget?: number, forceComplete?: boolean, skillKey?: string) =>
    RESP<{ run_id: string }>(axios.post('/api/reasoning-flow/test-run/start', {
      requirement_text: text,
      explicit_budget: budget,
      force_complete: forceComplete ?? true,
    }, { params: skillKey ? { skill_key: skillKey } : undefined })),
}
