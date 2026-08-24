import type { RequirementRule, RuleStatus, RuleType } from '@/api/requirementRules'

export type RuleGroupKey = 'understand' | 'dictionary' | 'strategy'
export type RuleLayout = 'table' | 'capacity' | 'fallback' | 'check'

export interface RuleGroup {
  key: RuleGroupKey
  label: string
  hint: string
  types: RuleType[]
}

export interface RuleTypeMeta {
  key: RuleType
  label: string
  group: RuleGroupKey
  hint: string
  layout: RuleLayout
}

export const RULE_GROUPS: RuleGroup[] = [
  { key: 'understand', label: '需求引导', hint: '判断明确度、映射预算、识别委托与用户意图', types: ['clarity', 'budget', 'delegation_phrases', 'model_action_phrases', 'kp_action_phrases'] },
  { key: 'dictionary', label: '语义字典', hint: '把客户表达归一化为平台、品类、内存代际与厂商/单位', types: ['category_alias', 'platform_series_map', 'cpu_mem_generation', 'cpu_vendor_map', 'type_alias', 'gpu_brand_map', 'spec_unit_patterns'] },
  { key: 'strategy', label: '选型策略', hint: '机型套餐、规格边界、方案校验与功耗/合规策略', types: ['type_package', 'spec_rule', 'raid_level_map', 'capacity_match', 'fallback_order', 'check_rule', 'workload_map', 'compliance_map', 'gpu_form_map', 'power_calibration'] },
]

export const RULE_TYPE_META: Record<RuleType, RuleTypeMeta> = {
  clarity: { key: 'clarity', label: '明确度判定', group: 'understand', hint: '按需求信号判定 explicit / partial / unclear', layout: 'table' },
  budget: { key: 'budget', label: '预算映射', group: 'understand', hint: '预算区间与代表件选择策略', layout: 'table' },
  category_alias: { key: 'category_alias', label: '品类别名', group: 'dictionary', hint: '客户品类词到 KP 品类键的映射', layout: 'table' },
  platform_series_map: { key: 'platform_series_map', label: '平台系列映射', group: 'dictionary', hint: '平台关键词到产品系列的映射', layout: 'table' },
  cpu_mem_generation: { key: 'cpu_mem_generation', label: 'CPU→内存代际', group: 'dictionary', hint: 'CPU 型号规则到内存代际的映射', layout: 'table' },
  type_package: { key: 'type_package', label: '机型类型套餐', group: 'strategy', hint: '机型关键词到标准品类套餐', layout: 'table' },
  spec_rule: { key: 'spec_rule', label: '规格匹配', group: 'strategy', hint: '未明确时的默认规格边界', layout: 'table' },
  raid_level_map: { key: 'raid_level_map', label: 'RAID 级别映射', group: 'strategy', hint: 'RAID 级别到阵列卡建议', layout: 'table' },
  capacity_match: { key: 'capacity_match', label: '容量匹配', group: 'strategy', hint: '容量匹配容差与接口默认值', layout: 'capacity' },
  fallback_order: { key: 'fallback_order', label: '选型放宽', group: 'strategy', hint: '机型候选的逐级放宽顺序', layout: 'fallback' },
  check_rule: { key: 'check_rule', label: '方案检查', group: 'strategy', hint: '方案生成后的自检开关', layout: 'check' },
  type_alias: { key: 'type_alias', label: '类型别名', group: 'dictionary', hint: '场景/类型关键词→目录规范类型名', layout: 'table' },
  cpu_vendor_map: { key: 'cpu_vendor_map', label: 'CPU 厂商映射', group: 'dictionary', hint: 'CPU 厂商/系列→产品系列与件侧匹配', layout: 'table' },
  gpu_brand_map: { key: 'gpu_brand_map', label: 'GPU 品牌词表', group: 'dictionary', hint: 'GPU 品牌→替代件同义词（NVIDIA/AMD 等）', layout: 'table' },
  spec_unit_patterns: { key: 'spec_unit_patterns', label: '规格单位正则', group: 'dictionary', hint: '规格单位→匹配正则（GB/W/核 等）', layout: 'table' },
  workload_map: { key: 'workload_map', label: '工作负载映射', group: 'strategy', hint: '工作负载→显存/卡数/意图（跑大模型等）', layout: 'table' },
  compliance_map: { key: 'compliance_map', label: '合规映射', group: 'strategy', hint: '国产化/合规→平台与配件白名单/排除', layout: 'table' },
  gpu_form_map: { key: 'gpu_form_map', label: 'GPU 形态映射', group: 'strategy', hint: 'GPU 数量→机箱形态（单卡→2U，多卡→4U）', layout: 'table' },
  power_calibration: { key: 'power_calibration', label: '功耗/电源校准', group: 'strategy', hint: 'CPU TDP、常项功耗、标准 PSU 档位与高功耗 GPU 词表', layout: 'table' },
  delegation_phrases: { key: 'delegation_phrases', label: '委托话术', group: 'understand', hint: '客户委托词（你推荐/随便/不懂/帮我选）', layout: 'table' },
  model_action_phrases: { key: 'model_action_phrases', label: '机型意图词', group: 'understand', hint: '自己配/推荐/重选/取消 判定词', layout: 'table' },
  kp_action_phrases: { key: 'kp_action_phrases', label: '配件意图词', group: 'understand', hint: '确认/重选/取消 判定词', layout: 'table' },
}

export const RULE_TYPE_OPTIONS = Object.values(RULE_TYPE_META).map((m) => ({ value: m.key, label: m.label }))

export const STATUS_OPTIONS: Array<{ value: RuleStatus; label: string }> = [
  { value: 'active', label: 'active' },
  { value: 'testing', label: 'testing' },
  { value: 'draft', label: 'draft' },
  { value: 'archived', label: 'archived' },
]

function oneLine(body: any): string {
  if (!body || typeof body !== 'object') return '—'
  return JSON.stringify(body)
}

export function ruleSummary(r: RequirementRule): string {
  const b = r.body || {}
  switch (r.type) {
    case 'clarity':
      return `${b.level || '—'} · 权重 ${b.weight ?? '—'}${b.explain ? ` · ${b.explain}` : ''}`
    case 'budget': {
      const range = b.range || {}
      const min = range.min == null ? '不限' : range.min
      const max = range.max == null ? '不限' : range.max
      return `${min} - ${max} · ${b.strategy?.label || b.strategy?.representative_pick || '—'}`
    }
    case 'cpu_mem_generation':
      return `${b.pattern || '—'} → ${b.mem_type || '—'}`
    case 'category_alias':
      return Array.isArray(b.aliases) ? b.aliases.join(' / ') : '—'
    case 'platform_series_map':
      return `${b.series || '—'}：${Array.isArray(b.keywords) ? b.keywords.join('、') : '—'}`
    case 'type_package':
      return `${b.type_keyword || '—'}：${Array.isArray(b.categories) ? b.categories.join(' / ') : '—'}`
    case 'spec_rule':
      return `${b.category || '—'} ${b.spec_key || '—'} ${b.op || ''} ${b.value ?? ''}${b.unit || ''}`
    case 'raid_level_map':
      return `${b.level || '—'} → ${b.category || '—'}${Array.isArray(b.prefer_models) ? `（${b.prefer_models.join('/')}）` : ''}`
    case 'capacity_match':
      return `${b.strategy || '—'} · 容差 ${b.tolerance ?? '—'}`
    case 'fallback_order':
      return Array.isArray(b.order) ? b.order.join(' → ') : '—'
    case 'check_rule': {
      const checks = b.checks || {}
      const enabled = Object.entries(checks).filter(([, v]) => v).map(([k]) => k)
      return enabled.length ? enabled.join('、') : '未启用自检'
    }
    default:
      return oneLine(b)
  }
}
