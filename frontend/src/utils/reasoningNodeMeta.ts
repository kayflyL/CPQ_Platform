/**
 * 需求分析画布 · 节点元数据（单一真源）
 * palette / 节点卡 / 抽屉标题 / 试运行时间线 label 共用，避免三处重复且口径不一。
 * 注意：这里只描述「节点身份」，不承载后端执行逻辑；执行语义由后端 orchestrator 按 type 派发。
 * 图标用 Ant Design 线性图标（与全站设计系统一致，替代 emoji），tone 控制柔和底色（现代感分组色）。
 */
import type { Component } from 'vue'
import {
  DesktopOutlined, ToolOutlined, BuildOutlined,
  FileDoneOutlined, FileTextOutlined, MessageOutlined,
} from '@ant-design/icons-vue'

export type NodeTone = 'blue' | 'purple' | 'green' | 'orange' | 'cyan' | 'gray'

export interface ReasoningNodeMeta {
  type: string
  /** 中文名（palette / 节点卡主 label / 抽屉标题） */
  name: string
  /** 职能一句话（节点卡 desc + palette 说明） */
  desc: string
  /** 数据来源（节点卡 tags） */
  sources?: string[]
  /** 线性图标（Ant Design，与全站一致） */
  icon?: Component
  /** 柔和底色分组色 */
  tone?: NodeTone
  /** AI 失效兜底节点 */
  fallback?: boolean
  /** 可选节点 */
  optional?: boolean
}

export type ReasoningNodeType = 'input' | 'agent' | 'assemble' | 'output'

export const REASONING_NODE_GROUPS: Array<{ name: string; types: string[] }> = [
  { name: '输入输出节点', types: ['input', 'output'] },
  { name: '智能体节点', types: ['agent_fill', 'model_reason', 'kp_reason', 'agent'] },
  { name: '组装节点', types: ['compose'] },
]

export const REASONING_NODE_META: Record<string, ReasoningNodeMeta> = {
  agent: {
    type: 'agent', name: '智能体节点', icon: ToolOutlined, tone: 'blue',
    desc: '由 LLM 决策并调用工具完成一个子任务',
    sources: ['工具目录', '数据来源'],
  },
  input: {
    type: 'input', name: '输入节点', icon: FileTextOutlined, tone: 'gray',
    desc: '接收用户输入并注入技能上下文',
    sources: ['用户输入'],
  },
  output: {
    type: 'output', name: '输出节点', icon: FileDoneOutlined, tone: 'green',
    desc: '生成最终输出',
    sources: ['输出模板'],
  },
  agent_fill: {
    type: 'agent_fill', name: '智能对话填表 Agent', icon: MessageOutlined, tone: 'blue',
    desc: '会对话、会查目录确认在售/系列、边答边填线索登记表；选型交给下游',
    sources: ['对话', '工具目录', '线索登记表'],
  },
  model_reason: {
    type: 'model_reason', name: '机型选型', icon: DesktopOutlined, tone: 'blue',
    desc: '按需求与在售目录匹配，选定机型',
    sources: ['在售机型', '规则目录'],
  },
  kp_reason: {
    type: 'kp_reason', name: '配件选型', icon: ToolOutlined, tone: 'blue',
    desc: '按需求与机型能力，匹配内存/盘/网卡/RAID/电源等',
    sources: ['配件库', '规格规则', '需求摘要'],
  },
  compose: {
    type: 'compose', name: '方案组装·BOM', icon: BuildOutlined, tone: 'green',
    desc: '把机型 + KP 组装成整机 BOM 方案草稿',
    sources: ['build_plan'],
  },
}

export type ReasoningNodeKind = 'agent' | 'output'

export const RUNTIME_TYPE_TO_GENERIC: Record<string, ReasoningNodeType> = {
  agent_fill: 'agent',
  model_reason: 'agent',
  kp_reason: 'agent',
  compose: 'assemble',
}

export const REASONING_NODE_KIND: Record<string, ReasoningNodeKind> = {
  input: 'output',
  agent: 'agent',
  assemble: 'output',
  output: 'output',
  agent_fill: 'agent',
  model_reason: 'agent',
  kp_reason: 'agent',
  compose: 'output',
}

export const NODE_DEFAULT_CONFIG: Record<ReasoningNodeType, Record<string, any>> = {
  input: {},
  agent: { enabled_tools: [], max_iterations: 6, system_prompt: '', rule_types: [] },
  assemble: { rule_types: [], template: '', output_schema: {} },
  output: { rule_types: [], template: '', output_schema: {} },
}

export function nodeArchetype(type?: string): ReasoningNodeType {
  if (!type) return 'agent'
  return RUNTIME_TYPE_TO_GENERIC[type] || (type as ReasoningNodeType)
}

export function reasoningNodeKind(type?: string): ReasoningNodeKind {
  if (!type) return 'output'
  return REASONING_NODE_KIND[type] || 'output'
}

export const REASONING_CFG_TYPES: string[] = [
  'input',
  'agent', 'output',
  'agent_fill', 'model_reason', 'kp_reason', 'compose',
]

export function reasoningNodeMeta(type?: string): ReasoningNodeMeta | null {
  if (!type) return null
  return REASONING_NODE_META[type] || null
}

/** 展示名：已知类型 → 中文名；未知（旧 flow / 自定义）→ 用存库 label */
export function reasoningNodeName(typeOrKey?: string, fallback?: string): string {
  const m = reasoningNodeMeta(typeOrKey)
  return m?.name || fallback || typeOrKey || ''
}

/** 试运行时间线 label：step key 命中已知类型 → 中文名，否则用后端广播 label */
export function stepDisplayLabel(key?: string, storedLabel?: string): string {
  if (!key) return storedLabel || ''
  const m = reasoningNodeMeta(key)
  return m?.name || storedLabel || key
}
