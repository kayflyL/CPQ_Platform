/**
 * 推理步骤中文摘要 + 节点徽标文案（ReasoningPanel 与策略中心试运行面板共用）。
 * 输入各节点 step_done 的 payload，返回一句话摘要 / 精简徽标。
 *
 * payload 形状（reasoning_executor._dispatch 各节点返回值）：
 * - compose:         { plans_count, warning? }
 */
export const STEP_COPY: Record<string, (p: any) => string> = {
  text_clean: (p) => {
    const r = p?.report || []
    if (!r.length) return '文本格式规整，无需清洗。'
    return `做了输入清洗：${r.map((it: any) => it.rule === 'noise' ? `去掉${it.removed || '噪音'}` : it.rule === 'char_fix' ? `${it.from}→${it.to}` : '表格行归一').join('、')}。`
  },
  understand: (p) => {
    if (!p?.called) return '需求理解未产出（空文本/异常）。'
    if (p?.sufficient === false) {
      const miss = p?.missing_critical?.length ? `：缺 ${p.missing_critical.join('、')}` : ''
      return `需求信息不足，反问补全${miss}。`
    }
    const st = p?.server_type_name ? p.server_type_name : '未定类型'
    const sf = [p?.series, p?.form].filter(Boolean).join('·')
    const via = p?.source === 'llm' ? '（AI 理解）' : (p?.source || '').startsWith('extract_only') ? '（规则兜底）' : ''
    return `需求理解：${st}${sf ? '·' + sf : ''}${via}。`
  },
  gap_analyze: (p) => {
    const miss = p?.missing_fields?.length ? `，缺：${p.missing_fields.join('、')}` : ''
    return `信息${p?.level === 'explicit' ? '已足够，直接推进' : '不足，需反问'}${miss}。`
  },
  llm_ask: (p) => {
    if (p?.skip) return '信息已足够，无需反问。'
    const why = p?.why ? `（${p.why}）` : ''
    return p?.question ? `反问：${p.question}${why}` : '反问补全信息。'
  },
  scene_decide: (p) => {
    if (!p?.determined) return '还判断不出场景，先确认用途。'
    const name = p?.scene_name || '通用计算服务器'
    const sf = [p?.series, p?.form].filter(Boolean).join(' ')
    const ev = (p?.evidence || []).join('、')
    return `判断为「${name}」${sf ? `（${sf}）` : ''}${ev ? `，依据：${ev}` : ''}。`
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
  budget_check: (p) => {
    if (!p?.checked) return '预算校验：跳过（无预算）。'
    const parts = []
    if (p?.over_budget_count) parts.push(`${p.over_budget_count} 个超预算`)
    else parts.push('全部在预算内')
    if (p?.underspend_count) parts.push(`${p.underspend_count} 个预算未用足一半（可升级）`)
    return `预算校验：${parts.join('，')}。`
  },
  llm_audit: (p) => {
    if (!p?.called) return p?.reason === 'disabled' ? 'AI 方案校对未开启，规则硬校验兜底。' : 'AI 方案校对未调用。'
    if (p?.reason === 'llm_error' || p?.reason === 'node_error') return `AI 方案校对失败已降级规则校对：${p?.error || ''}。`
    const refs = p?.references?.length ?? 0
    const parts: string[] = []
    if (p?.issue_plans) parts.push(`${p.issue_plans} 个方案有意图级疑点`)
    else parts.push('未发现意图级硬问题')
    return `AI 方案校对（参考 ${refs} 个同平台案例）：${parts.join('，')}，耗时 ${((p?.duration_ms ?? 0) / 1000).toFixed(1)}s。`
  },
  llm_confirm: (p) => {
    const n = p?.count ?? p?.items?.length ?? 0
    return n ? `待确认 ${n} 项（机型/配件推荐）` : '无确认项，直接放行。'
  },
  review: (p) => {
    const blocked = p?.blocked ?? 0
    let s = `方案就绪：共 ${p?.plans ?? 0} 个方案${blocked ? `，${blocked} 个不通过需调整` : ''}。`
    const llm = p?.llm
    if (llm) {
      if (llm.reason === 'disabled') s += ' AI 方案校对未开启，纯规则硬校验。'
      else if (llm.called === false) s += ' AI 方案校对未生效（AI 总开关未启用）。'
      else if (llm.error) s += ` AI 方案校对失败已降级：${llm.error}。`
      else s += ` AI 方案校对检查了 ${llm.plans_checked ?? 0} 个方案${llm.issue_plans ? `，${llm.issue_plans} 个有疑点需人工确认` : '，未发现意图级硬问题'}。`
    }
    return s
  },
}

/** 节点徽标精简文案（贴画布节点右上，试运行回放时展示） */
export const STEP_BADGE: Record<string, (p: any) => string> = {
  text_clean: () => '清洗',
  understand: (p) => {
    if (!p?.called) return '?'
    if (p?.sufficient === false) return '反问'
    if (p?.source === 'llm') return p?.server_type_name || 'AI理解'
    return '规则'   // extract_only_*（AI 关/失败·离线兜底）
  },
  gap_analyze: (p) => (p?.level === 'explicit' ? '明确' : `缺${(p?.missing_fields || []).length}`),
  llm_ask: (p) => (p?.skip ? '✓' : '反问'),
  scene_decide: (p) => {
    const n = p?.scene_name || ''
    if (n.includes('AI')) return 'AI'
    if (n.includes('存储')) return '存储'
    return n ? '通用' : '?'
  },
  model_reason: (p) => (p?.source === 'llm' ? `AI选${p?.count ?? 0}` : `规则${p?.count ?? 0}`),
  kp_reason: (p) => (p?.source === 'llm' || p?.source === 'llm+rule' ? `AI配${p?.kp_count ?? 0}` : `配${p?.kp_count ?? 0}`),
  compose: (p) => `${p?.plans_count ?? 0}方案`,
  budget_check: (p) => (p?.over_budget_count ? `${p.over_budget_count}超` : '✓'),
  llm_audit: (p) => {
    if (!p?.called) return '规则'
    if (p?.reason === 'llm_error' || p?.reason === 'node_error') return 'LLM✗'
    return p?.issue_plans ? `${p.issue_plans}疑` : 'LLM✓'
  },
  llm_confirm: (p) => `${p?.count ?? p?.items?.length ?? 0}确认`,
  review: (p) => {
    const blocked = p?.blocked ?? 0
    return blocked ? `${blocked}⚠` : '✓'
  },
}
