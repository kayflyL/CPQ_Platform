/** 工具目录元数据（类别标签唯一出处）：目录页分组与工具卡片角标共用 */
export const TOOL_CATEGORY_LABELS: Record<string, string> = {
  selection: '选型决策',
  data: '数据查询',
  cost: '成本核算',
  quote: '报价生成',
}

export function toolCategoryLabel(category?: string): string {
  return TOOL_CATEGORY_LABELS[String(category || '')] || String(category || '')
}

export const TOOL_CATEGORY_ORDER = ['selection', 'data', 'cost', 'quote']
