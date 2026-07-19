/** 类别专用规格字段族（基于真实数据归纳；未列出的类别走扩展属性兜底）。
 *  PartsLibrary 与 PartPicker 共享 —— 卡片/选项里显示哪些 specs 键由此决定。
 *  原 PartsLibrary.vue 的 CATEGORY_FIELDS 抽出至此（系统性梳理，非打地鼠）。 */
export interface SpecField {
  key: string
  label: string
  icon?: string
  unit?: string
  type: 'number' | 'text' | 'tags'
}

export const SPEC_FIELDS: Record<string, SpecField[]> = {
  '电源':       [{ key: 'wattage', label: '功率', icon: '⚡', unit: 'W', type: 'number' }],
  'CPU':        [{ key: 'tdp', label: 'TDP', icon: '🔥', unit: 'W', type: 'number' }],
  'GPU':        [{ key: 'tdp', label: 'TDP', icon: '🔥', unit: 'W', type: 'number' }],
  '散热器':     [{ key: 'tdp', label: 'TDP', icon: '🔥', unit: 'W', type: 'number' }],
  '机箱':       [{ key: 'bays', label: '盘位数', icon: '📦', type: 'number' }, { key: 'form', label: '形态', icon: '📐', type: 'text' }],
  '背板':       [{ key: 'bays', label: '盘位数', icon: '📦', type: 'number' }, { key: 'bt', label: '背板类型', icon: '🔌', type: 'text' }],
  '前面板线缆': [{ key: 'group_size', label: '分组大小', icon: '🔗', type: 'number' }, { key: 'drive_bays', label: '适用盘位', icon: '🎯', type: 'tags' }, { key: 'backplane', label: '适用背板', icon: '🎯', type: 'tags' }],
  'IO线缆':     [{ key: 'group_size', label: '分组大小', icon: '🔗', type: 'number' }, { key: 'drive_bays', label: '适用盘位', icon: '🎯', type: 'tags' }, { key: 'backplane', label: '适用背板', icon: '🎯', type: 'tags' }],
  '后面板Riser':[{ key: 'io_slot', label: 'IO槽位', icon: '🧩', type: 'text' }, { key: 'option_type', label: '选项类型', icon: '🧩', type: 'text' }],
  'OCP':        [{ key: 'io_slot', label: 'IO槽位', icon: '🧩', type: 'text' }, { key: 'option_type', label: '选项类型', icon: '🧩', type: 'text' }],
}

/** 取某类别的字段族；未配置返回 []。 */
export function specFieldsFor(category?: string): SpecField[] {
  if (!category) return []
  return SPEC_FIELDS[category] || []
}

/** 把一条 specs + 字段族渲染成紧凑摘要（如 "360W" 或 "12盘位 · 2U"），给下拉选项/卡片用。 */
export function specSummary(specs: Record<string, any> | undefined, category?: string): string {
  if (!specs) return ''
  const fields = specFieldsFor(category)
  const parts: string[] = []
  for (const f of fields) {
    const v = specs[f.key]
    if (v === undefined || v === null || v === '') continue
    const text = Array.isArray(v) ? v.join('/') : String(v)
    parts.push(f.unit ? `${text}${f.unit}` : text)
  }
  return parts.join(' · ')
}
