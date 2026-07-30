/**
 * 选型规则引擎 —— 纯求值逻辑（无 vue/pinia 依赖，可独立单测）。
 *
 * 声明式 WHEN(条件)→THEN(动作) 规则求值。由 selectionRules store 加载 active 规则后调用。
 * body schema 见 backend compatibility_rule_repo.DEFAULT_RULES：
 *   when: { all?:[cond], any?:[cond] } | cond   cond = { field, op, value }
 *   then: { action, ... }   action ∈ require/exclude/derive/filter/recommend
 *   字段寻址：kp.<category>.qty / kp.<category>.spec.<key> / config.series / config.sata_qty / opportunity.platform_type
 *
 * 抽出为纯模块的目的：(1) 可用 node:test 独立单测保住正确性下限；(2) 与 store 状态解耦，
 * 未来后端兜底执行可参照同一份语义实现。
 */
import type { CompatibilityRule } from '@/api/compatibilityRules'

export type RuleActionKind = 'require' | 'exclude' | 'derive' | 'filter' | 'recommend'
export type RuleSeverity = 'conflict' | 'require' | 'info'

export interface RuleAction {
  ruleId: number
  ruleName: string
  action: RuleActionKind
  severity: RuleSeverity
  desc: string
  target?: string
  offenders?: string[]            // exclude：违规的字段值集合
  // filter 专用
  filterScope?: string            // server_model / kp
  filterField?: string
  filterOp?: string
  filterValue?: any
  // derive 专用（算术型：basis÷per→数量）
  deriveTarget?: string
  deriveQty?: number
  derivePer?: number              // 算术型每组基数（per），供消费端透明展示"每组 N"
  // derive 赋值型专用（条件→固定值，如 背板类型=tri）
  assignField?: string
  assignValue?: any
}

// ── 求值上下文（消费端构建）──
export interface RuleContext {
  /** 按 category 聚合的 KP 配件：qty=数量合计，items=原始行（含 enrich 的 spec/pn），spec=该类典型规格 */
  kp: Record<string, { qty: number; items: any[]; spec: Record<string, any> }>
  config: { series?: string; model?: string; form?: string; sata_qty?: number; drive_kinds?: string[] }
  opportunity: { platform_type?: string }
}

const FIELD_PATH_RE = /^(kp|config|opportunity)\./

type Cond = { field: string; op: string; value: any }

/** 解析字段路径 → context 实际值。"kp.GPU.qty"/"config.series"/"opportunity.platform_type" */
export function resolveField(ctx: RuleContext, field: string | undefined): any {
  if (!field) return undefined
  const parts = field.split('.')
  const root = parts[0]
  if (root === 'kp') {
    const node = ctx.kp[parts[1]]
    if (!node) return undefined
    if (parts[2] === 'qty') return node.qty
    if (parts[2] === 'spec') return node.spec?.[parts[3]]
    return undefined
  }
  if (root === 'config') return (ctx.config as any)[parts[1]]
  if (root === 'opportunity') return (ctx.opportunity as any)[parts[1]]
  return undefined
}

/** 解析值：若 v 是字段路径（kp./config./opportunity. 开头）则取 context 值，否则按字面量。 */
export function resolveValue(ctx: RuleContext, v: any): any {
  if (typeof v === 'string' && FIELD_PATH_RE.test(v)) {
    const resolved = resolveField(ctx, v)
    if (resolved !== undefined) return resolved
  }
  return v
}

export function evalOp(actual: any, op: string, expected: any): boolean {
  if (op === 'exists') return actual !== undefined && actual !== null && actual !== ''
  switch (op) {
    case '>=': return Number(actual) >= Number(expected)
    case '<=': return Number(actual) <= Number(expected)
    case '>': return Number(actual) > Number(expected)
    case '<': return Number(actual) < Number(expected)
    case '==': return actual == expected
    case '!=': return actual != expected
    case 'in': return Array.isArray(expected) && expected.includes(actual)
    case 'contains': return Array.isArray(actual) ? actual.includes(expected) : String(actual ?? '').includes(expected)
    default: return false
  }
}

export function evalCondition(ctx: RuleContext, cond: any): boolean {
  if (!cond || !cond.field) return true
  return evalOp(resolveField(ctx, cond.field), cond.op, resolveValue(ctx, cond.value))
}

export function evalWhen(ctx: RuleContext, when: any): boolean {
  if (!when) return true
  if (Array.isArray(when.all)) return when.all.every((c: Cond) => evalCondition(ctx, c))
  if (Array.isArray(when.any)) return when.any.some((c: Cond) => evalCondition(ctx, c))
  if (when.field) return evalCondition(ctx, when)
  return true
}

export function parseCat(target: string | undefined): string {
  if (!target) return ''
  return target.startsWith('kp.') ? target.slice(3) : target
}

/** 盘类型 key（与 ctx.config.sata_qty/sas_qty/nvme_qty、CORE_DRIVE_KINDS 一致）*/
const DRIVE_KIND_KEYS = ['SATA', 'SAS', 'NVMe'] as const
/**
 * 盘类型规范化：把任意来源（KP 件 specs.interface/kind/type，或型号名文本）的盘类型字符串
 * 统一成 SATA/SAS/NVMe（与 ctx.config.*_qty / CORE_DRIVE_KINDS 一致），大小写无关；无法识别返回 undefined。
 * 消费端策略（见 kpSummaryFor / ConfigWizard kpSummary）：优先结构化 specs，缺失（无 pn / excel 新件无 specs）再回退型号名嗅探。
 */
export function normalizeDriveKind(raw: any): string | undefined {
  const up = String(raw ?? '').toUpperCase()
  return DRIVE_KIND_KEYS.find(k => up.includes(k.toUpperCase()))
}

export function readItemField(item: any, field: string): any {
  if (!field) return undefined
  if (field.startsWith('spec.')) return item?.spec?.[field.slice(5)]
  return item?.[field]
}

/** 对单条命中规则求值 THEN，产出动作。 */
export function evalThen(ctx: RuleContext, rule: CompatibilityRule): RuleAction[] {
  const then: any = rule.body?.then
  if (!then) return []
  const desc = rule.body?.desc || rule.name
  const base = { ruleId: rule.id, ruleName: rule.name, desc }
  switch (then.action as RuleActionKind) {
    case 'exclude': {
      const cat = parseCat(then.target)
      const node = ctx.kp[cat]
      if (!node || node.items.length < 2) return []
      const field = then.unique_field || 'pn'
      const vals = node.items.map(it => readItemField(it, field)).filter(v => v !== undefined && v !== null && v !== '')
      const uniq = [...new Set(vals.map(String))]
      if (uniq.length > 1) {
        return [{ ...base, action: 'exclude', severity: 'conflict', target: cat, offenders: uniq, desc: then.desc || desc }]
      }
      return []
    }
    case 'require': {
      const cat = parseCat(then.target)
      const node = ctx.kp[cat]
      const minQty = then.min_qty != null ? Number(resolveValue(ctx, then.min_qty)) || 1 : 1
      const haveQty = node?.qty || 0
      let specOk = true
      if (then.spec_constraint && node) {
        specOk = node.items.some(it =>
          Object.entries(then.spec_constraint).every(([k, v]) => String(it.spec?.[k] ?? '') === String(v)))
      }
      if (haveQty < minQty || !specOk) {
        const lack = haveQty < minQty ? `缺少 ${cat}（需 ${minQty}，现有 ${haveQty}）` : `${cat} 规格不符`
        return [{ ...base, action: 'require', severity: 'require', target: cat, desc: then.desc || lack }]
      }
      return []
    }
    case 'derive': {
      // 赋值型：then 带 field+value（条件→固定值，如 背板类型=tri），区别于算术型 basis÷per
      if (then.field && 'value' in then) {
        return [{ ...base, action: 'derive', severity: 'info', assignField: then.field, assignValue: then.value, desc: then.desc || desc }]
      }
      const basisVal = Number(resolveValue(ctx, then.basis))
      const per = Number(then.per) || 1
      if (!Number.isFinite(basisVal) || basisVal <= 0) return []
      const qty = then.round === 'ceil' ? Math.ceil(basisVal / per) : Math.floor(basisVal / per)
      const cat = parseCat(then.target)
      const haveQty = ctx.kp[cat]?.qty || 0
      if (haveQty < qty) {
        return [{ ...base, action: 'derive', severity: 'info', deriveTarget: cat, deriveQty: qty, derivePer: per, desc: then.desc || `${cat} 建议配 ${qty}（现有 ${haveQty}）` }]
      }
      return []
    }
    case 'filter': {
      return [{
        ...base, action: 'filter', severity: 'info',
        filterScope: then.scope, filterField: then.field, filterOp: then.op,
        filterValue: resolveValue(ctx, then.value),
        desc: then.desc || desc,
      }]
    }
    case 'recommend': {
      return [{ ...base, action: 'recommend', severity: 'info', target: then.target, desc: then.desc || desc }]
    }
    default:
      return []
  }
}

/** 对一组配置 context 跑全部 active 规则，返回命中动作清单。 */
export function evaluateRules(rules: CompatibilityRule[], ctx: RuleContext): RuleAction[] {
  const out: RuleAction[] = []
  for (const r of rules) {
    if (r.status !== 'active') continue
    if (!evalWhen(ctx, r.body?.when)) continue
    out.push(...evalThen(ctx, r))
  }
  return out
}

/**
 * 对一组配置 context，求某赋值型字段的目标值（如背板类型 config.bp_type）。
 * 按 rules 原顺序，首条 when 命中且 then 为赋值型 derive + assignField===field 的规则生效（short-circuit）。
 * 因此「更具体的规则放前、宽泛规则放后」。无命中返回 undefined（由消费端兜底，如 bpType 的 ?? 'dc'）。
 */
export function evalAssignValue(rules: CompatibilityRule[], ctx: RuleContext, field: string): any {
  for (const r of rules) {
    if (r.status !== 'active') continue
    const then: any = r.body?.then
    if (!then || then.action !== 'derive' || !(then.field && 'value' in then)) continue
    if (then.field !== field) continue
    if (evalWhen(ctx, r.body?.when)) return then.value
  }
  return undefined
}
