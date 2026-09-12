/** 归一化料号 —— PartPicker 的统一数据形态。
 *  KP（kp.kp_parts）/ L6（l6.parts_master）/ PSU 选项三种源经 usePartAdapter 映射后都用这个。
 *  不合并两表，只做形状映射（见 memory: kp-parts-unification-roadmap）。 */
export interface PickerItem {
  pn: string
  name: string
  category?: string
  specs?: Record<string, any>
  unit_price?: number
  currency?: string
  brand?: string
  supplier?: string
  /** 最近一次价格日期（KP 源）；L6/PSU 无此字段 */ 
  price_date?: string
  description?: string
  applicable?: Record<string, any> | { series?: string[] } | null
  source: 'kp' | 'l6' | 'psu'
}
