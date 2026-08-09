/**
 * 需求分析画布 · 节点元数据（单一真源）
 * palette / 节点卡 / 抽屉标题 / 试运行时间线 label 共用，避免三处重复且口径不一。
 * 注意：这里只描述「节点身份」，不承载后端执行逻辑；执行语义由后端 orchestrator 按 type 派发。
 * 图标用 Ant Design 线性图标（与全站设计系统一致，替代 emoji），tone 控制柔和底色（现代感分组色）。
 */
import type { Component } from 'vue'
import {
  RobotOutlined, NodeIndexOutlined, ScanOutlined, QuestionCircleOutlined, AimOutlined,
  DesktopOutlined, ToolOutlined, CheckCircleOutlined, BuildOutlined, MoneyCollectOutlined,
  AuditOutlined, SyncOutlined, ShakeOutlined, FileDoneOutlined, BranchesOutlined, ClearOutlined,
  ControlOutlined, SafetyCertificateOutlined,
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

export const REASONING_NODE_GROUPS: Array<{ name: string; types: string[] }> = [
  { name: '理解交互', types: ['understand', 'llm_ask'] },
  { name: '编排策略', types: ['orchestrator'] },
  { name: '决策推理', types: ['model_reason', 'kp_reason'] },
  { name: '产出执行', types: ['spec_compliance', 'result_check', 'compose', 'budget_check', 'llm_audit', 'audit_fix', 'llm_confirm', 'review'] },
  { name: '分支控制', types: ['condition'] },
  { name: '可选', types: ['text_clean'] },
]

export const REASONING_NODE_META: Record<string, ReasoningNodeMeta> = {
  understand: {
    type: 'understand', name: '需求理解', icon: RobotOutlined, tone: 'blue',
    desc: 'LLM 填表理解需求 + 领域知识注入 + 在售目录锚定；抽不全→反问，AI 失效→规则兜底',
    sources: ['词表', '别名表', '在售目录'],
  },
  extract: {
    type: 'extract', name: '规则理解兜底', icon: NodeIndexOutlined, tone: 'gray', fallback: true,
    desc: 'AI 失效时的分词 + 词表命中兜底解析（离线可跑）',
    sources: ['词表', 'jieba'],
  },
  gap_analyze: {
    type: 'gap_analyze', name: '缺口分析', icon: ScanOutlined, tone: 'cyan',
    desc: '已填槽位 vs 期望清单 → 明确度 + 缺失项（LLM 可选解释缺什么）',
    sources: ['期望槽位清单'],
  },
  llm_ask: {
    type: 'llm_ask', name: '智能反问', icon: QuestionCircleOutlined, tone: 'purple',
    desc: 'LLM 按完整上下文生成策略性问题（带选项/理由）；AI 关→目录引导兜底',
    sources: ['在售目录', '缺口'],
  },
  scene_decide: {
    type: 'scene_decide', name: '场景判定', icon: AimOutlined, tone: 'purple',
    desc: '需求信号 → AI/存储/通用 × 系列 × 形态，带证据白盒',
    sources: ['场景映射'],
  },
  model_reason: {
    type: 'model_reason', name: '机型推理', icon: DesktopOutlined, tone: 'blue',
    desc: 'LLM ReAct 调 select_models 锁机型 + 理由；失败→规则四级兜底',
    sources: ['在售机型'],
  },
  kp_reason: {
    type: 'kp_reason', name: '配件推理', icon: ToolOutlined, tone: 'blue',
    desc: 'LLM ReAct 调 pick_kp_parts 定配件 + 理由；失败→规则三级匹配',
    sources: ['配件库', '规格规则'],
  },
  spec_compliance: {
    type: 'spec_compliance', name: '规格合规校验', icon: CheckCircleOutlined, tone: 'green',
    desc: '需求规格 vs 实配：AI 缺卡自动补 / 型号降级 / 内存代际不符标 issue',
    sources: ['规格规则'],
  },
  compose: {
    type: 'compose', name: '方案组装', icon: BuildOutlined, tone: 'green',
    desc: '确定性红线：把选型决策组装成整机 BOM（价格/兼容性/PSU/线缆派生）',
    sources: ['build_plan'],
  },
  budget_check: {
    type: 'budget_check', name: '预算校验', icon: MoneyCollectOutlined, tone: 'orange',
    desc: '超预算/欠预算标注 + 可选自动降配（确定性）',
    sources: ['预算映射'],
  },
  llm_audit: {
    type: 'llm_audit', name: '方案校对', icon: AuditOutlined, tone: 'purple',
    desc: 'LLM 意图级审查（few-shot 案例）+ 规则硬校验兜底',
    sources: ['bom_cases'],
  },
  audit_fix: {
    type: 'audit_fix', name: '审计自纠', icon: SyncOutlined, tone: 'green',
    desc: '检出问题（缺卡/内存不足）→ 确定性重跑链自纠再审计',
    sources: ['审计规则'],
  },
  llm_confirm: {
    type: 'llm_confirm', name: '决策确认', icon: ShakeOutlined, tone: 'purple',
    desc: '汇总机型/配件推荐 + 理由，给用户确认/调整后重跑（可选）',
    sources: [],
  },
  review: {
    type: 'review', name: '方案就绪', icon: FileDoneOutlined, tone: 'green',
    desc: '产出方案清单 + BOM 明细 + 对话式推荐（确定性红线）',
    sources: ['BOM 模板'],
  },
  condition: {
    type: 'condition', name: '条件分支', icon: BranchesOutlined, tone: 'orange',
    desc: '按表达式求值选真/假分支（simpleeval 安全求值）',
    sources: ['表达式'],
  },
  orchestrator: {
    type: 'orchestrator', name: '编排配置', icon: ControlOutlined, tone: 'gray',
    desc: '编排器全局策略：结构化记忆 / 白盒计划 / 并行 / AI 增强预算（不执行，只提供配置）',
    sources: ['记忆', '推进策略'],
  },
  result_check: {
    type: 'result_check', name: '方案自检', icon: SafetyCertificateOutlined, tone: 'green',
    desc: '确定性：结果完整性 + 必填核心件 + 数量合理性；失败可自动触发重跑',
    sources: ['检查项配置'],
  },
  text_clean: {
    type: 'text_clean', name: '文本清洗', icon: ClearOutlined, tone: 'gray', optional: true,
    desc: '去噪音 / 全角归一 / 表格行归一（AI 与规则共用前置，可删）',
    sources: ['归一规则'],
  },
}

export const REASONING_CFG_TYPES = [
  'understand', 'extract', 'gap_analyze', 'llm_ask', 'orchestrator', 'scene_decide', 'model_reason', 'kp_reason',
  'spec_compliance', 'result_check', 'compose', 'budget_check', 'llm_audit', 'audit_fix', 'llm_confirm', 'review', 'condition', 'text_clean',
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
