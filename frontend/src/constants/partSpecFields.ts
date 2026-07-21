/** 通用规格字段族 —— 只列两类字段：
 *  ① 跨料号通用、需要标签/单位引导的（功率 / TDP / 盘位 / 形态）；
 *  ② 结构化 tags 多选（适用盘位 / 适用背板）—— 必须留在字段族，扩展属性的文本模型会把数组退化成字符串。
 *  单值差异化键（线缆类型 kind、背板类型 bt、GPU 型号 model、IO 槽位、选项类型、分组大小等）
 *  一律走「扩展属性」自由键值对，用户按需填写；代码层按约定键名读 specs.X（见 derivation_engine / l6_chassis_repo）。 */
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
  '背板':       [{ key: 'bays', label: '盘位数', icon: '📦', type: 'number' }],
  '前面板线缆': [{ key: 'drive_bays', label: '适用盘位', icon: '🎯', type: 'tags' }, { key: 'backplane', label: '适用背板', icon: '🎯', type: 'tags' }],
  'IO线缆':     [{ key: 'drive_bays', label: '适用盘位', icon: '🎯', type: 'tags' }, { key: 'backplane', label: '适用背板', icon: '🎯', type: 'tags' }],
}

/** 取某类别的字段族；未配置返回 []。 */
export function specFieldsFor(category?: string): SpecField[] {
  if (!category) return []
  return SPEC_FIELDS[category] || []
}

// ──────────────────────────────────────────────────────────────
// 扩展属性 schema 字典（编辑表单用）—— 唯一渲染源。
// 料号编辑表单只剩两段：基础信息 + 扩展属性；扩展属性的每个键按此 schema 渲染输入控件。
//   - enum-single: 下拉单选（如 option_type）
//   - enum-multi : 下拉多选（如 io_slot、chassis，一颗料可属多槽/多机型）
//   - free-tags  : 自由标签，输入后回车成 chip、可连续追加（如 form="2U"/"4U"）
//   - number / text: 常规
// 未登记的键默认按 free-tags 处理（满足"任意值回车追加"的交互）。
export type AttrType = 'enum-single' | 'enum-multi' | 'free-tags' | 'number' | 'text'
export interface AttrSchema { label: string; type: AttrType; options?: string[]; unit?: string }

export const ATTR_SCHEMA: Record<string, AttrSchema> = {
  io_slot:     { label: 'IO 槽位',   type: 'enum-multi',  options: ['IO1', 'IO2', 'IO3', 'IO4', 'OCP'] },
  option_type: { label: '选项类型',  type: 'enum-single', options: ['x16', 'x8', 'nvme', 'sata', 'ocp_x8', 'ocp_x16'] },
  chassis:     { label: '适用机型',  type: 'enum-multi',  options: ['Orion', 'Polaris'] },
  backplane:   { label: '适用背板',  type: 'enum-multi',  options: ['三模', '直连'] },
  kind:        { label: '线缆种类',  type: 'enum-single', options: ['SATA', 'SAS', 'NVMe'] },
  bt:          { label: '背板类型',  type: 'enum-single', options: ['tri', 'dc'] },
  wattage:     { label: '功率',      type: 'number', unit: 'W' },
  tdp:         { label: 'TDP',       type: 'number', unit: 'W' },
  bays:        { label: '盘位数',    type: 'number' },
  group_size:  { label: '分组大小',  type: 'number' },
  form:        { label: '形态',      type: 'free-tags' },
  drive_bays:  { label: '适用盘位',  type: 'free-tags' },
  model:       { label: 'GPU 型号',  type: 'text' },
}

/** 未登记键的默认类型：free-tags（任意值回车追加）。 */
export function attrType(key: string): AttrType {
  return ATTR_SCHEMA[key]?.type ?? 'free-tags'
}
export function attrSchema(key: string): AttrSchema | undefined {
  return ATTR_SCHEMA[key]
}
export function attrOptions(key: string): { label: string; value: string }[] {
  return (ATTR_SCHEMA[key]?.options || []).map(v => ({ label: v, value: v }))
}
export const ATTR_KEY_OPTIONS = Object.entries(ATTR_SCHEMA).map(
  ([k, v]) => ({ label: `${k} · ${v.label}`, value: k }),
)

/** 类别 → 建议预填的属性键（编辑表单类别切换时自动补空行，保留旧"规格参数"段的引导，不另起段）。 */
export const SUGGESTED_KEYS_BY_CATEGORY: Record<string, string[]> = {
  '电源':       ['wattage'],
  'CPU':        ['tdp'],
  'GPU':        ['tdp', 'model'],
  '散热器':     ['tdp'],
  '机箱':       ['bays', 'form'],
  '背板':       ['bays', 'bt'],
  '前面板线缆': ['kind', 'drive_bays', 'backplane'],
  'IO线缆':     ['kind', 'drive_bays', 'backplane'],
  '后面板Riser': ['io_slot', 'option_type', 'chassis'],
  'OCP':        ['io_slot', 'option_type', 'chassis'],
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
