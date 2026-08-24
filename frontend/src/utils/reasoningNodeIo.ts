/**
 * 节点 IO 元数据：声明每个需求分析节点读取/产出的真实业务变量。
 * 抽屉顶部「输入 / 输出契约」与试运行时间线共用这一份真源，避免再写散落的硬编码说明。
 */
export interface IoVar { name: string; from?: string; desc?: string }
export type NodeIo = { in: IoVar[]; out: IoVar[] }

export const NODE_IO: Record<string, NodeIo> = {
  input: {
    in: [],
    out: [
      { name: 'requirement_text', desc: '客户自然语言需求原文' },
      { name: 'opportunity_id', desc: '商机上下文' },
      { name: 'normalized_text', desc: '规范化后的需求文本' },
    ],
  },
  agent_fill: {
    in: [
      { name: 'requirement_text', from: 'input', desc: '需求原文' },
      { name: 'last_user_answer', desc: '上一轮反问后客户回答（对话回合）' },
      { name: 'catalog', desc: '在售类型/系列/形态白名单' },
    ],
    out: [
      { name: 'ext', desc: '映射到真实线索登记表字段的槽位信号' },
      { name: 'purchase_qty', desc: '整机采购台数' },
      { name: 'missing_fields', desc: '信息不足时输出的缺失关键字段' },
      { name: 'awaiting_input', desc: '信息不足时反问暂停，等待用户补充' },
    ],
  },
  model_reason: {
    in: [
      { name: 'ext', from: 'agent_fill', desc: '线索登记字段' },
      { name: 'catalog', desc: '在售机型目录' },
    ],
    out: [
      { name: 'baselines', desc: '选中的机型骨架' },
      { name: 'model_reason', desc: '选型来源与理由' },
    ],
  },
  kp_reason: {
    in: [
      { name: 'ext', from: 'agent_fill', desc: '线索登记字段' },
      { name: 'baselines', from: 'model_reason', desc: '机型骨架' },
    ],
    out: [
      { name: 'kp_by_model', desc: '每个机型对应的关键配件' },
      { name: 'kp_parts', desc: '展平后的关键配件清单' },
    ],
  },
  compose: {
    in: [
      { name: 'baselines', from: 'model_reason', desc: '机型骨架' },
      { name: 'kp_by_model', from: 'kp_reason', desc: '配件清单' },
      { name: 'ext.psu_signal', from: 'agent_fill', desc: '电源信号' },
    ],
    out: [
      { name: 'plans', desc: '按真实 BOM 模板组装后的 bom_scheme 配置数据' },
    ],
  },
  output: {
    in: [
      { name: 'plans', from: 'compose', desc: 'BOM 方案配置数据' },
      { name: 'ext', from: 'agent_fill', desc: '线索登记字段' },
      { name: 'opportunity_id', from: 'input', desc: '商机上下文' },
    ],
    out: [
      { name: 'requirement', desc: '写回真实线索登记表' },
      { name: 'bom_scheme', desc: '写回真实方案配置草稿' },
      { name: 'business_entity', desc: '交付给 AI Office / 商机详情页' },
    ],
  },
}
