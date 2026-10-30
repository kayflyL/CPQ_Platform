/** 产物渲染形状注册表（P2 产物契约域化·前端半）：kind → shape。
 *
 * 域新增产物只需两步，前端零改：
 *   1. 后端 builder 产出对应形状的数据契约；
 *   2. 在此登记 kind → shape（未登记的 kind 落 raw 原样 JSON，白盒不装懂）。
 *
 * shape ∈ document | table | form | scheme | raw：
 *   document  {markdown}                       → MarkdownContent 渲染
 *   table     {rows, columns?, hintLines?, summary?, unmatched?, waived?} → 通用表格
 *   form      线索登记表（RequirementForm + fromSlots 装填）
 *   scheme    bomScheme（props 注入，SchemeEditor 只读）
 *   raw       原样 JSON
 */
export const ARTIFACT_SHAPES: Record<string, string> = {
  requirement_text: 'document',
  data_report: 'document',
  document: 'document',
  l6_chassis: 'table',
  kp_table: 'table',
  requirement_slots: 'form',
  bom_scheme: 'scheme',
  plans: 'raw',
  parts_proposal: 'raw',
}

export function shapeOf(kind?: string): string {
  return ARTIFACT_SHAPES[(kind || '').trim()] || 'raw'
}
