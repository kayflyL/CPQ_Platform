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
  normalize_input: {
    in: [{ name: 'requirement_text', from: '输入', desc: '原始需求文本' }],
    out: [
      { name: 'normalized_text', desc: '归一后的统一格式文本（extract 消费）' },
      { name: 'normalize_report', desc: '归一报告（改了什么，白盒）' },
    ],
  },
  extract: {
    in: [{ name: 'normalized_text', from: 'normalize_input', desc: '归一文本' }, { name: 'requirement_text', from: '输入' }],
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
  scene_analysis: {
    in: [
      { name: 'ext.categories/series/form/usage', from: 'extract' },
      { name: 'requirement_text', from: '输入' },
      { name: 'opportunity', from: '商机上下文', desc: '行业/客户类型' },
      { name: 'catalog_type_name', from: 'ask_user', desc: '目录引导已选类型（权威）' },
    ],
    out: [
      { name: 'scene', desc: 'scene_name/series/form + 置信度 + 证据（白盒）' },
      { name: 'missing_fields', desc: '场景无法确定时追加「场景」待反问' },
    ],
  },
  cond_scene: {
    in: [{ name: 'missing_fields', from: 'scene_analysis/clarity_check' }],
    out: [{ name: '__branch', desc: 'true→select_baseline 选型 / false→ask_user 反问场景' }],
  },
  confirm_series: {
    in: [
      { name: 'scene', from: 'scene_analysis', desc: 'series/series_source（明说/推断）' },
      { name: 'confirmed_series', from: '输入', desc: '用户已确认的系列（跨轮）' },
    ],
    out: [
      { name: 'series_ready', desc: '系列已确认/明说 → cond_scene 放行选型' },
      { name: 'awaiting_input', desc: '需确认系列时暂停（pipeline 停）' },
    ],
  },
  select_baseline: {
    in: [
      { name: 'scene', from: 'scene_analysis', desc: '类型/系列/形态候选范围' },
      { name: 'ext.usage/series/form', from: 'extract' },
    ],
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
  llm_understand: {
    in: [
      { name: 'requirement_text', from: '输入' },
      { name: 'ext', from: 'extract', desc: '规则抽取结果（LLM 只补缺，规则赢）' },
      { name: 'catalog', from: '实时 DB', desc: '在售类型/机型/系列/型号家族词（白名单）' },
    ],
    out: [
      { name: 'llm_slots', desc: 'RequirementSlots 契约（槽位+置信度+证据+预算+意图+缺失+追问）' },
      { name: 'llm_report', desc: 'LLM 状态/变更/校验错误/覆盖度（白盒）' },
      { name: 'ext', desc: '合并后（规则赢、只补缺：系列/形态/类型/预算/CPU/内存/盘/GPU/网卡/电源）' },
    ],
  },
  slot_validate: {
    in: [{ name: 'llm_slots', from: 'llm_understand' }, { name: 'ext', from: 'extract/llm_understand' }],
    out: [
      { name: 'slot_validation', desc: '白名单闸门结果 + LLM vs 规则冲突/低置信度 confirm_items + 覆盖度' },
    ],
  },
  confirm: {
    in: [{ name: 'slot_validation.confirm_items', from: 'slot_validate', desc: '冲突/低置信度项（默认采纳）' }, { name: 'confirm_decisions', from: '输入', desc: '用户决策 {item_id: accept|ignore}' }],
    out: [
      { name: 'confirm_applied', desc: '应用明细（写 requirement_samples 反馈闭环）' },
      { name: 'confirm_pending', desc: '待用户确认（run_pipeline 广播 need_confirm）' },
    ],
  },
  llm_ask: {
    in: [{ name: 'catalog_stage', from: '输入', desc: '目录引导阶段' }, { name: 'llm_report.questions', from: 'llm_understand', desc: 'LLM 一次性缺失项追问' }],
    out: [{ name: 'awaiting_input', desc: '反问暂停（need_input）' }],
  },
  llm_audit: {
    in: [
      { name: 'plans', from: 'compose', desc: '整机方案（校对对象）' },
      { name: 'requirement_text', from: '输入' },
      { name: 'bom_cases', from: '实时 DB', desc: '同平台 few-shot 参考案例（不跨平台硬套）' },
    ],
    out: [
      { name: 'llm_audits', desc: '每方案意图级校对 passed/issues → review 合并进 plan.audit' },
      { name: 'llm_audit_report', desc: 'LLM 状态/耗时/参考案例（trace 已落库）' },
    ],
  },
  condition: {
    in: [{ name: 'ctx 变量', desc: '白名单 series/form/clarity/budget/clarity_capped…' }],
    out: [{ name: '__branch', desc: 'true/false 分支路由' }],
  },
}
