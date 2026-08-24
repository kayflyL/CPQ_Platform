/**
 * 推理步骤中文摘要 + 节点徽标文案（策略中心试运行面板使用）。
 * 输入各节点 step_done 的 payload，返回一句话摘要 / 精简徽标。
 *
 * payload 形状（reasoning_executor._dispatch 各节点返回值）：
 * - compose:         { plans_count, warning? }
 */
export const STEP_COPY: Record<string, (p: any) => string> = {
  input: () => '已接收客户需求，准备进入线索登记。',
  agent_fill: (p) => {
    if (!p?.called) return '智能对话填表 Agent 未产出（空文本/异常）。'
    if (p?.sufficient === false) {
      const miss = p?.missing_critical?.length ? `：缺 ${p.missing_critical.join('、')}` : ''
      return p?.question ? `反问：${p.question}${miss}` : `信息不足，反问补全${miss}。`
    }
    const st = p?.server_type_name ? p.server_type_name : '未定类型'
    const sf = [p?.series, p?.form].filter(Boolean).join('·')
    return `智能对话填表：${st}${sf ? '·' + sf : ''}。`
  },
  model_reason: (p) => {
    const names = (p?.matches || []).map((m: any) => m.name)
    const src = p?.source === 'llm' ? 'AI 选定' : '规则选定'
    const reason = p?.reason ? `；理由：${String(p.reason).slice(0, 60)}` : ''
    return `${src}机型：${names.join(' / ') || '（无）'}${reason}。`
  },
  kp_reason: (p) => {
    const cats = Object.keys(p?.by_category || {})
    const src = p?.source === 'llm+rule' || p?.source === 'llm' ? 'AI 确认' : '规则匹配'
    return `${src}配件：${p?.kp_count ?? 0} 件${cats.length ? `（${cats.join('、')}）` : ''}${p?.reason ? `；${String(p.reason).slice(0, 50)}` : ''}。`
  },
  compose: (p) => p?.warning
    ? `${p.warning}`
    : `组合出 ${p?.plans_count ?? 0} 张整机方案，挑一张看看 👇`,
  output: (p) => `方案已生成并写入业务表单${p?.output_kind === 'bom_scheme_draft' ? '（BOM 方案草稿）' : ''}。`,
}

/** 节点徽标精简文案（贴画布节点右上，试运行回放时展示） */
export const STEP_BADGE: Record<string, (p: any) => string> = {
  input: () => '输入',
  agent_fill: (p) => {
    if (!p?.called) return '?'
    if (p?.sufficient === false) return '反问'
    return p?.server_type_name || '填表'
  },
  model_reason: (p) => (p?.source === 'llm' ? `AI选${p?.count ?? 0}` : `规则${p?.count ?? 0}`),
  kp_reason: (p) => (p?.source === 'llm' || p?.source === 'llm+rule' ? `AI配${p?.kp_count ?? 0}` : `配${p?.kp_count ?? 0}`),
  compose: (p) => `${p?.plans_count ?? 0}方案`,
  output: () => '交付',
}
