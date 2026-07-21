/** 料号一级「部段」分类 —— 对应报价表 4 个 STEP。
 *  section 是一级主导航（基准/前面板/后面板/电源），细 category 降为段内二级筛选。
 *  与后端 scripts/add_section_to_parts.py 的 CATEGORY_TO_SECTION 同源。 */
export type PartSectionName = '基准件' | '前面板件' | '后面板件' | '电源件'

/** 左栏主导航顺序 */
export const SECTION_ORDER: PartSectionName[] = ['基准件', '前面板件', '后面板件', '电源件']

/** 部段 → 语义样式 token（马卡龙语义色，参见 glass-console-system） */
export const SECTION_LABELS: Record<PartSectionName, { label: string; desc: string }> = {
  基准件: { label: '基准件', desc: 'STEP1 · 机箱/主板/背板/散热/IO模组…' },
  前面板件: { label: '前面板件', desc: 'STEP2 · 盘-背板连线' },
  后面板件: { label: '后面板件', desc: 'STEP3 · Riser/OCP/后硬盘模组' },
  电源件: { label: '电源件', desc: 'STEP4 · PSU（按功耗推导）' },
}

/** 新建料号时按 category 推断默认部段；用户可在表单手改覆盖 */
export const CATEGORY_TO_SECTION: Record<string, PartSectionName> = {
  机箱: '基准件', 托盘: '基准件', 主板: '基准件', 散热器: '基准件',
  底盘件: '基准件', 后IO板: '基准件', 背板: '基准件', 滑轨: '基准件',
  导风罩: '基准件', 标签: '基准件', 电源线: '基准件', IO线缆: '基准件',
  前面板线缆: '前面板件',
  后面板Riser: '后面板件', OCP: '后面板件', GPU电源线: '后面板件',
  电源: '电源件',
}

export function defaultSectionFor(category?: string): PartSectionName | undefined {
  if (!category) return undefined
  return CATEGORY_TO_SECTION[category]
}
