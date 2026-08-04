/**
 * CRE 选型规则元数据 SSOT —— 兼容性规则编辑器(CompatibilityRuleEditor) 与
 * 规则拓扑图(CompatibilityImpactGraph / ImpactNode) 共用的唯一真相源。
 *
 * 集中三类元数据，杜绝 label / 色值 / 符号 / 展示文案散落多处裸字面导致漂移：
 *   ① 规则类型（label + 语义色 CSS var + VueFlow edge/SVG 需要的真实 hex）
 *   ② 操作符（符号即展示文本）
 *   ③ CRE ctx 字段命名空间与 config/opportunity 字段中文
 *   ④ 拓扑图 / 卡片展示文案与符号
 *
 * 注意：config.* 是 CRE 引擎上下文派生字段，不属于商机字段表
 *       也不属于料号 spec 字段族(partSpecFields)，故在此独立维护。
 */
import type { RuleType } from '@/api/compatibilityRules'

// ── ① 规则类型 ──
export interface RuleTypeDef { value: RuleType; label: string; cssVar: string; hex: string }
export const RULE_TYPE_DEFS: RuleTypeDef[] = [
  { value: 'require',   label: '必配/依赖', cssVar: 'var(--cpq-accent-primary)', hex: '#1677ff' },
  { value: 'exclude',   label: '互斥',     cssVar: 'var(--cpq-accent-danger)',  hex: '#ff4d4f' },
  { value: 'derive',    label: '派生',     cssVar: 'var(--cpq-color-purple)',  hex: '#a855f7' },
  { value: 'filter',    label: '过滤',     cssVar: 'var(--cpq-accent-warning)', hex: '#fa8c16' },
  { value: 'recommend', label: '推荐',     cssVar: 'var(--cpq-color-success)',  hex: '#52c41a' },
]
export const RULE_TYPE_MAP = Object.fromEntries(RULE_TYPE_DEFS.map(t => [t.value, t])) as Record<RuleType, RuleTypeDef>
/** a-select 选项形式（编辑器类型下拉用） */
export const RULE_TYPE_OPTIONS = RULE_TYPE_DEFS.map(t => ({ value: t.value, label: t.label }))

// ── ② 操作符（symbol 即展示文本）──
export interface RuleOpDef { value: string; symbol: string }
export const RULE_OP_DEFS: RuleOpDef[] = [
  { value: '>=', symbol: '≥' }, { value: '<=', symbol: '≤' },
  { value: '>', symbol: '>' }, { value: '<', symbol: '<' },
  { value: '==', symbol: '=' }, { value: '!=', symbol: '≠' },
  { value: 'in', symbol: '属于' }, { value: 'contains', symbol: '包含' },
  { value: 'exists', symbol: '有值' },
]
export const RULE_OP_MAP = Object.fromEntries(RULE_OP_DEFS.map(o => [o.value, o.symbol])) as Record<string, string>
/** a-select 选项形式（编辑器操作符下拉用） */
export const RULE_OP_OPTIONS = RULE_OP_DEFS.map(o => ({ value: o.value, label: o.symbol }))

// ── ③ CRE ctx 字段命名空间与字段中文 ──
export const FIELD_NS_LABEL: Record<string, string> = { config: '配置', opportunity: '商机' }
/** config.* 字段中文（CRE 引擎上下文派生字段） */
export const CONFIG_FIELD_LABEL: Record<string, string> = {
  series: '系列', model: '机型', form: '形态', bays: '盘位',
  sata_qty: 'SATA 盘数', sas_qty: 'SAS 盘数', nvme_qty: 'NVMe 盘数',
  drive_kinds: '盘类型', bp_type: '背板类型',
}
/** opportunity.* 字段中文 */
export const OPP_FIELD_LABEL: Record<string, string> = { platform_type: '平台类型' }
/** 命名空间下某字段的中文 label，未登记回退原 key */
export function ctxFieldLabel(ns: string, key: string): string {
  const tbl = ns === 'config' ? CONFIG_FIELD_LABEL : ns === 'opportunity' ? OPP_FIELD_LABEL : null
  return tbl ? (tbl[key] ?? key) : key
}

// ── ④ 拓扑图 / 卡片展示文案与符号（字面集中，编辑器与拓扑图共用）──
export const RULE_GRAPH_TEXT = {
  // 节点 pill
  whenPill: '条件',
  thenPill: '结果',
  // 状态 / 逻辑连接
  alwaysActive: '⚡ 总是生效',
  noCondition: '无条件',
  matchAny: '满足任一',
  logicAll: '且',
  logicAny: '或',
  // 字段友好化
  nsJoin: '·',        // 命名空间/字段连接：GPU·数量 / 配置·背板类型
  listSep: ' · ',     // 结果项分隔：必配 · ≥1
  qtySuffix: '数量',
  // 动作前缀 / 标签
  requirePrefix: '必配',
  recommendLabel: '推荐',
  assignLabel: '赋值',
  deriveLabel: '派生',
  specLabel: '规格',
  // 符号
  eq: '=',
  assignEq: '= ',
  divideBy: ' ÷ ',
  // 互斥默认字段
  excludeDefaultField: 'pn',
  // 过滤作用域
  filterScope: { server_model: '候选机型', kp: 'KP 配件' } as Record<string, string>,
  // 取整方式
  round: { ceil: '向上取整', floor: '向下取整' } as Record<string, string>,
  // 空状态
  empty: '暂无可视化关系——规则需含 require / derive / exclude / filter 动作，且 WHEN 指向具体品类',
} as const

/** 互斥结果文案：同 {field} 不混搭 */
export function excludeText(uniqueField?: string): string {
  return `同 ${uniqueField || RULE_GRAPH_TEXT.excludeDefaultField} 不混搭`
}

// ── ⑤ 告警 severity 元数据（消费方 Workspace / ConfigWizard 实时校验面板共用）──
// 引擎对每条命中动作已赋 severity（exclude→conflict / require→require / derive·recommend·filter→info），
// 这里集中其展示属性（图标/标签/是否阻断），替换散落模板里的图标三元式硬编码。
export type AlertSeverity = 'conflict' | 'require' | 'info'
export interface AlertSeverityDef { value: AlertSeverity; icon: string; label: string; blocking: boolean }
export const ALERT_SEVERITY_DEFS: AlertSeverityDef[] = [
  { value: 'conflict', icon: '⚠', label: '冲突', blocking: true },  // exclude 互斥命中（如内存/CPU/GPU 混插）
  { value: 'require',  icon: '＋', label: '必配', blocking: true },  // require 缺配 / 规格不符
  { value: 'info',     icon: '💡', label: '建议', blocking: false }, // derive / recommend
]
const _ALERT_SEV_MAP = Object.fromEntries(ALERT_SEVERITY_DEFS.map(s => [s.value, s])) as Record<AlertSeverity, AlertSeverityDef>

/** 告警图标：按 severity 取（消费方替换图标三元式）*/
export function alertIcon(severity: AlertSeverity | string): string {
  return _ALERT_SEV_MAP[severity as AlertSeverity]?.icon ?? '💡'
}
/** severity 展示标签 */
export function alertLabel(severity: AlertSeverity | string): string {
  return _ALERT_SEV_MAP[severity as AlertSeverity]?.label ?? severity
}
/** 是否阻断级（conflict/require）——消费方据此决定是否进保存确认 */
export function isBlockingSeverity(severity: AlertSeverity | string): boolean {
  return !!_ALERT_SEV_MAP[severity as AlertSeverity]?.blocking
}

// ── ⑥ 规则业务分类（category）配色 SSOT ──
// category 是用户可自定义的开放标签（后端 DISTINCT 驱动，非固定枚举）。
// 故只给 seed 预置项指定「语义色」，再用马卡龙调色板按分类名稳定散列取色，
// 让用户新建的任意分类也拿到一致颜色——杜绝组件内裸写色值/三元式。
// seed 分类（与 backend DEFAULT_RULES 的 category 一致；过滤条/分组按此顺序排前）
export const RULE_CATEGORY_SEED: string[] = ['背板与线缆', '核心件互斥']
// seed 分类的语义色（互斥→红、线缆→紫，呼应规则类型色语义）
export const RULE_CATEGORY_COLOR: Record<string, string> = {
  '背板与线缆': 'var(--cpq-color-purple)',
  '核心件互斥': 'var(--cpq-accent-danger)',
}
// 马卡龙调色板（Glass Console 语义色同源），用户自建分类按名稳定散列落入
export const CATEGORY_PALETTE: string[] = [
  'var(--cpq-accent-primary)',
  'var(--cpq-color-success)',
  'var(--cpq-accent-warning)',
  'var(--cpq-color-purple)',
  'var(--cpq-accent-danger)',
]
/** 分类色：seed 项走语义色表，其余按名稳定散列取调色板；空分类走弱化文本色 */
export function categoryColor(name: string | null | undefined): string {
  if (!name) return 'var(--cpq-text-muted)'
  if (RULE_CATEGORY_COLOR[name]) return RULE_CATEGORY_COLOR[name]
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return CATEGORY_PALETTE[h % CATEGORY_PALETTE.length]
}
