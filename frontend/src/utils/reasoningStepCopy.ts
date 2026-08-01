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
  extract: (p) => {
    const kws = (p?.keywords || []).join('、')
    const sf = [p?.series, p?.form].filter(Boolean).join(' ')
    return `抓到关键信息：${kws || '（没抓到明显关键词）'}${sf ? `，场景像 ${sf}` : ''}。`
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
}

/** 节点徽标精简文案（贴画布节点右上，试运行回放时展示） */
export const STEP_BADGE: Record<string, (p: any) => string> = {
  extract: (p) => `${(p?.keywords || []).length}词`,
  select_baseline: (p) => `选${p?.count ?? 0}个`,
  match_kp: (p) => `配${p?.kp_count ?? 0}件`,
  compose: (p) => `${p?.plans_count ?? 0}方案`,
}
