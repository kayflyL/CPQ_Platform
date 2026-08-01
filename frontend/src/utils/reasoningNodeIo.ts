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
  extract: {
    in: [{ name: 'requirement_text', from: '输入', desc: '需求文本' }],
    out: [
      { name: 'ext', desc: 'keywords/categories/series/form/内存·CPU信号/多规格' },
      { name: 'budget', desc: '从文本抽取的预算（兜底）' },
    ],
  },
  clarity_check: {
    in: [{ name: 'ext', from: 'extract' }, { name: 'budget', from: '输入/extract' }, { name: 'force_complete', from: '输入' }],
    out: [
      { name: 'clarity', desc: 'explicit/partial/unclear' },
      { name: 'missing_fields', desc: '缺失字段清单' },
      { name: 'clarity_capped', desc: '死循环防护封顶标志' },
    ],
  },
  cond_clarity: {
    in: [{ name: 'clarity', from: 'clarity_check' }, { name: 'clarity_capped', from: 'clarity_check' }],
    out: [{ name: '__branch', desc: 'true→ask_user 反问 / false→select_baseline 选型' }],
  },
  ask_user: {
    in: [{ name: 'missing_fields', from: 'clarity_check' }],
    out: [
      { name: 'awaiting_input', desc: '暂停标志（pipeline 停）' },
      { name: 'question', desc: '反问话术（广播 need_input）' },
    ],
  },
  select_baseline: {
    in: [{ name: 'ext.usage/series/form', from: 'extract' }],
    out: [{ name: 'baselines', desc: '匹配的机型骨架列表' }],
  },
  match_kp: {
    in: [
      { name: 'baselines', from: 'select_baseline' },
      { name: 'ext.categories/keywords/signals', from: 'extract' },
      { name: 'budget', from: '输入' },
    ],
    out: [
      { name: 'kp_by_model', desc: '每机型配的 KP 件' },
      { name: 'kp_parts', desc: 'KP 件展平' },
    ],
  },
  compose: {
    in: [{ name: 'baselines', from: 'select_baseline' }, { name: 'kp_by_model', from: 'match_kp' }, { name: 'ext.psu_signal', from: 'extract' }],
    out: [{ name: 'plans', desc: '整机方案（含 summary/含税总价/折算）' }],
  },
  budget_check: {
    in: [{ name: 'plans', from: 'compose' }, { name: 'budget', from: '输入' }],
    out: [{ name: 'plans.over_budget/underspend', desc: '预算标注（不剔除）' }],
  },
  review: {
    in: [{ name: 'plans', from: 'compose' }, { name: 'ext', from: 'extract' }],
    out: [{ name: 'candidates_ready', desc: '广播方案清单给前端' }],
  },
  condition: {
    in: [{ name: 'ctx 变量', desc: '白名单 series/form/clarity/budget/clarity_capped…' }],
    out: [{ name: '__branch', desc: 'true/false 分支路由' }],
  },
  llm: {
    in: [{ name: '自定义', desc: '引用上游变量 + prompt' }],
    out: [{ name: '自定义', desc: 'LLM 输出注入 ctx' }],
  },
}
