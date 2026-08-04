/**
 * 推理步骤中文摘要 + 节点徽标文案（ReasoningPanel 与策略中心试运行面板共用）。
 * 输入各节点 step_done 的 payload，返回一句话摘要 / 精简徽标。
 *
 * payload 形状（reasoning_executor._dispatch 各节点返回值）：
 * - extract:         { keywords, categories, series, form, usage, server_type_name, chassis_categories, budget }
 * - select_baseline: { count, matches:[{config_id,name,series,form}] }
 * - match_kp:        { kp_count, by_category:{category:n}, unmatched_count }
 * - compose:         { plans_count, warning? }
 */
export const STEP_COPY: Record<string, (p: any) => string> = {
  normalize_input: (p) => {
    const r = p?.report || []
    if (!r.length) return '需求文本格式比较规整，直接进入关键词提取。'
    const parts = r.map((it: any) => it.rule === 'noise' ? `去掉${it.removed || '噪音'}` : it.rule === 'char_fix' ? `${it.from}→${it.to}` : '表格行归一')
    return `做了输入归一：${parts.join('、')}。`
  },
  extract: (p) => {
    const kws = (p?.keywords || []).join('、')
    const sf = [p?.series, p?.form].filter(Boolean).join(' ')
    // 2026-08 LLM 重构 P1：LLM 增强已从 extract 下线，收拢到 llm_understand 节点
    return `抓到关键信息：${kws || '（没抓到明显关键词）'}${sf ? `，场景像 ${sf}` : ''}。`
  },
  confirm_series: (p) => {
    if (p?.skip) return p.series ? `系列「${p.series}」已确认，继续选型。` : '系列已明说，继续选型。'
    return p?.series ? `推断系列「${p.series}」，问用户确认。` : '推不出系列，请用户选择系列。'
  },
  select_baseline: (p) => {
    const names = (p?.matches || []).map((m: any) => m.name)
    return `从机型库挑了 ${p?.count ?? 0} 个整机骨架${names.length ? `：${names.join(' / ')}` : ''}。`
  },
  match_kp: (p) => {
    const cats = Object.keys(p?.by_category || {})
    return `按需求配了 ${p?.kp_count ?? 0} 件 KP${cats.length ? `（${cats.join('、')}）` : ''}。`
  },
  compose: (p) => p?.warning
    ? `${p.warning}`
    : `组合出 ${p?.plans_count ?? 0} 张整机方案，挑一张看看 👇`,
  scene_analysis: (p) => {
    if (!p?.determined) return '还判断不出场景，先问你一下用途。'
    const name = p?.scene_name || '通用计算服务器'
    const sf = [p?.series, p?.form].filter(Boolean).join(' ')
    const ev = (p?.evidence || []).join('、')
    // 2026-08 LLM 重构 P1：LLM 增强已从 scene_analysis 下线，收拢到 llm_understand 节点
    return `判断为「${name}」${sf ? `（${sf}）` : ''}${ev ? `，依据：${ev}` : ''}。`
  },
  llm_understand: (p) => {
    if (!p?.called) return p?.reason === 'disabled' ? 'LLM 主理解未开启（节点开关默认关），规则直接出结果。' : 'LLM 主理解未调用。'
    if (p?.reason === 'global_ai_disabled') return 'LLM 主理解跳过：AI 总开关未启用。'
    if (p?.reason === 'llm_error') return `LLM 主理解调用失败已降级规则：${p?.error || ''}。`
    const parts: string[] = []
    if (p?.merged) parts.push(`LLM 补充 ${p.changes?.length ?? 0} 项（${(p.changes || []).join('、')}）`)
    else parts.push('LLM 已理解，无新增')
    if (p?.retried) parts.push('校验失败已带错重试')
    if (p?.errors?.length) parts.push(`仍有 ${p.errors.length} 处校验未过`)
    const cov = p?.coverage
    const covNote = cov?.total ? `槽位覆盖 ${cov.filled}/${cov.total}` : ''
    const intent = p?.intent_summary ? `意图：${p.intent_summary}` : ''
    return `LLM 主理解：${parts.join('；')}${covNote ? `，${covNote}` : ''}${intent ? `，${intent}` : ''}。`
  },
  slot_validate: (p) => {
    const parts: string[] = []
    if (p?.issues?.length) parts.push(`${p.issues.length} 处白名单外值已丢弃`)
    else parts.push('白名单校验通过')
    const confs = p?.confirm_items?.length ?? 0
    if (confs) parts.push(`${confs} 项需人工确认`)
    const cov = p?.coverage
    const covNote = cov?.total ? `覆盖 ${cov.filled}/${cov.total}` : ''
    return `槽位语义校验：${parts.join('，')}${covNote ? `，${covNote}` : ''}。`
  },
  confirm: (p) => {
    if (p?.skip) return '无 LLM 确认项，直接放行。'
    if (p?.awaiting) return `LLM 补充了 ${p.items?.length ?? 0} 项待确认（默认采纳，可改）。`
    const n = p?.count ?? p?.confirmed?.length ?? 0
    if (!n) return '无 LLM 确认项，直接放行。'
    const acc = (p?.confirmed || []).filter((c: any) => c.decision === 'accept').length
    const ig = (p?.confirmed || []).filter((c: any) => c.decision === 'ignore').length
    return `LLM 确认：采纳 ${acc} 项${ig ? `、忽略 ${ig} 项` : ''}。`
  },
  llm_ask: (p) => {
    if (p?.skip) return '信息已足够，无需反问。'
    return p?.question ? `反问：${p.question}` : '反问补全信息。'
  },
  llm_audit: (p) => {
    if (!p?.called) return p?.reason === 'disabled' ? 'LLM 方案校对未开启（默认关），规则硬校验兜底。' : 'LLM 方案校对未调用。'
    if (p?.reason === 'llm_error' || p?.reason === 'node_error') return `LLM 方案校对失败已降级规则校对：${p?.error || ''}。`
    const refs = p?.references?.length ?? 0
    const parts: string[] = []
    if (p?.issue_plans) parts.push(`${p.issue_plans} 个方案有意图级疑点`)
    else parts.push('未发现意图级硬问题')
    return `LLM 方案校对（参考 ${refs} 个同平台案例）：${parts.join('，')}，耗时 ${((p?.duration_ms ?? 0) / 1000).toFixed(1)}s。`
  },
  review: (p) => {
    const blocked = p?.blocked ?? 0
    const llm = p?.llm
    let s = `方案就绪：共 ${p?.plans ?? 0} 个方案${blocked ? `，${blocked} 个不通过需调整` : ''}。`
    if (llm) {
      if (llm.reason === 'disabled') s += ' LLM 方案校对未开启，纯规则硬校验。'
      else if (llm.called === false) s += ' LLM 方案校对未生效（AI 总开关未启用）。'
      else if (llm.error) s += ` LLM 方案校对失败已降级：${llm.error}。`
      else s += ` LLM 方案校对检查了 ${llm.plans_checked ?? 0} 个方案${llm.issue_plans ? `，${llm.issue_plans} 个有疑点需人工确认` : '，未发现意图级硬问题'}。`
    }
    return s
  },
}

/** 节点徽标精简文案（贴画布节点右上，试运行回放时展示） */
export const STEP_BADGE: Record<string, (p: any) => string> = {
  normalize_input: () => '归一',
  extract: (p) => `${(p?.keywords || []).length}词`,
  select_baseline: (p) => `选${p?.count ?? 0}个`,
  match_kp: (p) => `配${p?.kp_count ?? 0}件`,
  compose: (p) => `${p?.plans_count ?? 0}方案`,
  confirm_series: (p) => (p?.skip ? '✓' : '确认'),
  scene_analysis: (p) => {
    const n = p?.scene_name || ''
    if (n.includes('AI')) return 'AI'
    if (n.includes('存储')) return '存储'
    return n ? '通用' : '?'
  },
  llm_understand: (p) => {
    if (!p?.called) return '规则'
    if (p?.reason === 'llm_error') return 'LLM✗'
    return p?.merged ? `LLM+${p.changes?.length ?? 0}` : 'LLM✓'
  },
  slot_validate: (p) => {
    const n = p?.confirm_items?.length ?? 0
    return n ? `${n}待确认` : '✓'
  },
  confirm: (p) => {
    if (p?.skip) return '✓'
    if (p?.awaiting) return `${p.items?.length ?? 0}确认`
    const acc = (p?.confirmed || []).filter((c: any) => c.decision === 'accept').length
    const ig = (p?.confirmed || []).filter((c: any) => c.decision === 'ignore').length
    return ig ? `${acc}采${ig}忽` : `${acc}采`
  },
  llm_ask: (p) => (p?.skip ? '✓' : '反问'),
  llm_audit: (p) => {
    if (!p?.called) return '规则'
    if (p?.reason === 'llm_error' || p?.reason === 'node_error') return 'LLM✗'
    return p?.issue_plans ? `${p.issue_plans}疑` : 'LLM✓'
  },
  review: (p) => {
    const blocked = p?.blocked ?? 0
    return blocked ? `${blocked}⚠` : '✓'
  },
}
