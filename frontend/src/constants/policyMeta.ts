/**
 * 策略文档库元数据 SSOT —— 文档分类 + body 解析助手。
 *
 * 文档存 rules.strategies(domain=policy, type=document):
 *   name  = 标题
 *   body  = { module, category, sort_order, content_markdown }  ← PolicyDocBody（module 隔离各策略文档库）
 *   description = 摘要
 *
 * 分类枚举与后端 policy_doc_repo.DEFAULT_DOCS 的 category 字段对齐。
 */
/** 策略模块（文档库按此隔离：报价策略/选型配置各自独立内容）*/
export type StrategyModule = 'pricing' | 'selection' | 'requirement'
export const MODULE_DEFS: { value: StrategyModule; label: string }[] = [
  { value: 'pricing', label: '报价策略' },
  { value: 'selection', label: '选型配置' },
  { value: 'requirement', label: '需求分析' },
]

export interface PolicyDocBody {
  module: StrategyModule
  category: string
  sort_order: number
  content_markdown: string
}

/** 文档分类(对齐后端 seed 的 category)。
 * 分类不是语义状态,不带各自配色(Glass Console:卡片统一白玻璃,色彩只给语义态)。*/
export const DOC_CATEGORIES = [
  { value: '总览', label: '总览' },
  { value: '维度详解', label: '维度详解' },
  { value: '操作指南', label: '操作指南' },
  { value: '变更公告', label: '变更公告' },
  { value: '其他', label: '其他' },
] as const

export type DocCategory = (typeof DOC_CATEGORIES)[number]
export const DOC_CATEGORY_MAP = Object.fromEntries(
  DOC_CATEGORIES.map((c) => [c.value, c]),
) as Record<string, DocCategory>

/** 安全读取 strategy.body 为 PolicyDocBody(容错:缺字段给默认；module 缺失归 'pricing' 兼容存量) */
export function readDocBody(body: any): PolicyDocBody {
  return {
    module: body?.module === 'selection' || body?.module === 'requirement' ? body.module : 'pricing',
    category: typeof body?.category === 'string' ? body.category : '其他',
    sort_order: Number(body?.sort_order) || 0,
    content_markdown: typeof body?.content_markdown === 'string' ? body.content_markdown : '',
  }
}
