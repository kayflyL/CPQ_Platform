/**
 * 节点 IO 元数据（描述性，声明每个节点类型消费/产出的变量）。
 * executor 仍走隐式 ctx 不变；这里只给试运行/画布展示"变量流转"用——可解释性。
 * 参考：腾讯元器的节点显式输入/输出变量声明（下游引用祖先输出）。
 *
 * in  = 该节点读取的变量（来源：系统输入 / 上游节点输出）
 * out = 该节点写入 ctx 的变量（给下游消费）
 * 数据来自 reasoning_executor._dispatch 各 handler 的实际读写。
 */
export interface IoVar { name: string; from?: string; desc?: string }
export type NodeIo = { in: IoVar[]; out: IoVar[] }

export const NODE_IO: Record<string, NodeIo> = {
  understand: {
    in: [{ name: 'requirement_text', from: '输入', desc: '需求原文' }, { name: 'flow_configs', from: '画布', desc: '领域知识(词表)/目录白名单/案例参数' }],
    out: [
      { name: 'ext', desc: '槽位信号(类型/系列/形态/品类/内存/CPU/盘/GPU/网卡/电源/预算)' },
      { name: 'llm_slots', desc: 'LLM 填表契约（槽位+置信度+证据+意图）' },
      { name: 'source', desc: 'llm / extract_only_*（AI 走了 LLM 还是规则兜底）' },
    ],
  },
  gap_analyze: {
    in: [{ name: 'ext', from: 'understand', desc: '已理解槽位' }],
    out: [
      { name: 'clarity', desc: 'explicit/partial（信息是否足够）' },
      { name: 'missing_fields', desc: '缺失关键信息清单' },
      { name: 'clarity_capped', desc: '反问封顶标志' },
    ],
  },
  cond_gap: {
    in: [{ name: 'clarity', from: 'gap_analyze' }, { name: 'clarity_capped', from: 'gap_analyze' }],
    out: [{ name: '__branch', desc: 'true→llm_ask 反问 / false→scene_decide 继续' }],
  },
  llm_ask: {
    in: [{ name: 'missing_fields', from: 'gap_analyze' }, { name: 'ext', from: 'understand' }, { name: 'catalog', from: '实时 DB', desc: '在售类型/系列（选项白名单）' }],
    out: [
      { name: 'awaiting_input', desc: '反问暂停（need_input + question/options/why）' },
      { name: 'source', desc: 'llm / rule（LLM 策略提问还是目录引导兜底）' },
    ],
  },
  scene_decide: {
    in: [{ name: 'ext', from: 'understand', desc: '需求信号' }, { name: 'opportunity', from: '商机上下文' }],
    out: [{ name: 'scene', desc: 'scene_name/series/form + 置信度 + 证据（白盒）' }],
  },
  model_reason: {
    in: [{ name: 'ext', from: 'understand' }, { name: 'scene', from: 'scene_decide' }],
    out: [
      { name: 'baselines', desc: 'LLM 选定的机型骨架（数据由规则补全）' },
      { name: 'model_reason', desc: 'source=llm/rule + reason + ReAct 工具轨迹' },
    ],
  },
  kp_reason: {
    in: [{ name: 'ext', from: 'understand' }, { name: 'baselines', from: 'model_reason' }],
    out: [
      { name: 'kp_by_model', desc: '每机型配的 KP 件' },
      { name: 'kp_parts', desc: 'KP 件展平' },
      { name: 'kp_reason', desc: 'source=llm/rule + reason + ReAct 工具轨迹' },
    ],
  },
  compose: {
    in: [{ name: 'baselines', from: 'model_reason' }, { name: 'kp_by_model', from: 'kp_reason' }, { name: 'ext.psu_signal', from: 'understand' }],
    out: [{ name: 'plans', desc: '整机方案（确定性组装：价格/兼容性/PSU/线缆派生）' }],
  },
  budget_check: {
    in: [{ name: 'plans', from: 'compose' }, { name: 'budget', from: '输入' }],
    out: [{ name: 'plans.over_budget/underspend', desc: '预算标注（不剔除）' }],
  },
  llm_audit: {
    in: [{ name: 'plans', from: 'compose', desc: '整机方案（校对对象）' }, { name: 'requirement_text', from: '输入' }],
    out: [{ name: 'plan.audit', desc: '意图级校对 passed/issues → review 合并' }],
  },
  llm_confirm: {
    in: [{ name: 'model_reason', from: 'model_reason' }, { name: 'kp_reason', from: 'kp_reason' }],
    out: [{ name: 'confirm_items', desc: '推荐机型/配件 + 理由，供确认面板（可调整）' }],
  },
  review: {
    in: [{ name: 'plans', from: 'compose' }, { name: 'ext', from: 'understand' }],
    out: [{ name: 'candidates_ready', desc: '广播方案清单给前端' }],
  },
  text_clean: {
    in: [{ name: 'requirement_text', from: '输入', desc: '原始需求文本' }],
    out: [{ name: 'normalized_text', desc: '轻量清洗后的文本（understand 消费）' }, { name: 'report', desc: '清洗报告（白盒）' }],
  },
  condition: {
    in: [{ name: 'ctx 变量', desc: '白名单 clarity/missing_fields/clarity_capped…' }],
    out: [{ name: '__branch', desc: 'true/false 分支路由' }],
  },
}
