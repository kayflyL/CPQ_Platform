/** 工具目录元数据（类别标签唯一出处）：目录页分组与工具卡片角标共用 */
export const TOOL_CATEGORY_LABELS: Record<string, string> = {
  workflow: '需求分析 · 工作流',
  business: '商机 · 报价 · 办事',
  data: '数据 · 报表',
  self: '同事自身',
}

export function toolCategoryLabel(category?: string): string {
  return TOOL_CATEGORY_LABELS[String(category || '')] || String(category || '')
}

export const TOOL_CATEGORY_ORDER = ['workflow', 'business', 'data', 'self']
