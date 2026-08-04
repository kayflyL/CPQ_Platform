/**
 * 推理流可视化配置 API（/api/reasoning-flow）。
 * 推理流 DAG：5 节点 extract→select_baseline→match_kp→compose→review + 各节点参数 config。
 * 改节点 config 立即生效（下次推理用新参数）；三层兜底在 run_pipeline（DB 异常回退模块常量）。
 */
import axios from 'axios'
import type { Plan } from '@/api/reasoning'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export type ReasoningNodeKey = 'extract' | 'select_baseline' | 'match_kp' | 'compose' | 'review' | 'ask_user' | 'clarity_check' | 'budget_check' | 'scene_analysis' | 'cond_scene' | 'normalize_input' | 'llm_understand' | 'slot_validate' | 'llm_audit'

/** extract 节点配置（多词表体系：KP 表 + 机型表，左侧 DB 下拉动态） */
export interface LexiconEntry {
  key: string                                    // 左侧下拉选中的值（品类名 / 系列 / 形态 / 类型名）
  triggers: string[]                             // 右侧触发词
}
export interface Lexicon {
  id: string                                     // 词表 id（lex_kp / lex_model）
  name: string                                   // 词表显示名
  kind: 'kp' | 'model'                           // 决定左侧下拉数据源
  entries: LexiconEntry[]
}
export interface ExtractNodeConfig {
  keyword_limit?: number
  lexicons?: Lexicon[]                           // 新：多词表（两张主表）
  // 旧字段保留兼容已存配置；编辑器检测到旧结构自动转新
  category_lexicon?: Record<string, string[]>
  series_keywords?: string[]
  series_keyword_map?: Record<string, string>
  stopwords?: string[]
  engine_note?: string
}

/** review 节点配置（P6 产出形态；BOM 模板不在此节点） */
export interface ReviewNodeConfig {
  output_preset?: 'detailed' | 'standard' | 'concise'
  output_fields?: {
    show_price?: boolean
    merge_chassis_kp?: boolean
    currency?: string
    show_recommend_reason?: boolean
    show_missing_hint?: boolean
  }
}

export interface ReasoningNodeMeta {
  id: string
  type: string
  label: string
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
  get: () => RESP<{ flow: ReasoningFlow | null }>(axios.get('/api/reasoning-flow/')),
  listVersions: () => RESP<{ versions: ReasoningFlow[] }>(axios.get('/api/reasoning-flow/versions')),
  updateGraph: (graph: ReasoningGraph) =>
    RESP<ReasoningFlow>(axios.put('/api/reasoning-flow/graph', { graph })),
  updateNode: (nodeKey: ReasoningNodeKey, config: Record<string, any>) =>
    RESP<any>(axios.put(`/api/reasoning-flow/nodes/${nodeKey}`, { config })),
  activate: (flowId: number) =>
    RESP<ReasoningFlow>(axios.post(`/api/reasoning-flow/versions/${flowId}/activate`, {})),
  llmNodes: () => RESP<{ nodes: Array<{ id: string; type: string; label: string; enable_llm: boolean }> }>(axios.get('/api/reasoning-flow/llm-nodes')),
  testRun: (text: string, budget?: number, forceComplete?: boolean) =>
    RESP<TestRunResult>(axios.post('/api/reasoning-flow/test-run', {
      requirement_text: text,
      explicit_budget: budget,
      force_complete: forceComplete ?? true,
    })),
}
