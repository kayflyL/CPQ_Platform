/**
 * 上下文 provider 实现 — 当前三个域:
 * - quoteProvider: 报价工作台(商机 + 当前报价单配置)
 * - opportunityProvider: 商机详情页(商机概览 + 报价单列表)
 * - opportunityListProvider: 商机线索页(驾驶舱统计 + 业务排行)
 *
 * 未来加策略中心等:在此 export 新 provider,加到 contextProviders 数组即可。
 */
import type { ContextProvider, QuickAction } from './assistantContext'

export const quoteProvider: ContextProvider = {
  key: 'quote',
  label: '报价',
  match: (ctx) =>
    ctx.route.path === '/workspace' && !!ctx.store.opportunityInfo?.opportunity_id,
  async summarize(ctx) {
    const info = ctx.store.opportunityInfo as any
    if (!info?.opportunity_id) return ''
    const lines = [
      `商机：${info.customer_name || info.opportunity_id}`,
      `平台：${info.platform_type || '-'} / 机箱：${info.chassis_form || '-'}`,
      `数量：${info.total_qty || 0} 台`,
    ]
    if (info.quotation_id) lines.push(`当前报价单：${info.quotation_id}`)
    return lines.join('\n')
  },
}

export const opportunityProvider: ContextProvider = {
  key: 'opportunity',
  label: '商机',
  match: (ctx) =>
    ctx.route.path.startsWith('/opportunities/') && !!ctx.route.params.opportunityId,
  async summarize(ctx) {
    const oid = ctx.route.params.opportunityId as string
    if (!oid) return ''
    try {
      const r = await fetch(`/api/opportunities/${oid}`)
      const data = await r.json()
      const meta = data.meta || {}
      const quos = (data.quotations || []).filter((q: any) => q.status === 'active')
      return [
        `商机：${meta.customer_name || oid}`,
        `销售：${meta.sales_person || '-'} / FAE：${meta.fae || '-'}`,
        `平台：${meta.platform_type || '-'} / 机箱：${meta.chassis_form || '-'}`,
        `报价单数：${quos.length}`,
      ].join('\n')
    } catch {
      return ''
    }
  },
}

export const opportunityListProvider: ContextProvider = {
  key: 'opportunity-list',
  label: '商机线索',
  match: (ctx) => ctx.route.path === '/opportunities',
  async summarize(ctx) {
    try {
      // 从 URL query 获取周期参数（支持自定义区间）
      const query = ctx.route.query
      const params = new URLSearchParams()
      if (query.start && query.end) {
        params.set('start', query.start as string)
        params.set('end', query.end as string)
      } else {
        params.set('period', (query.period as string) || 'week')
      }

      // 调用驾驶舱摘要接口
      const r = await fetch(`/api/dashboard/summary?${params}`)
      const data = await r.json()

      // 提取关键字段
      const kpi = data.kpi || {}
      const platforms = (data.structure?.platforms || []).slice(0, 3)
      const topSales = (data.sales_rank?.top || []).slice(0, 3)

      // 构造上下文摘要
      const lines = [
        `【时间周期】${data.period_label || '当前'}`,
        `【核心指标】总商机 ${kpi.total_opportunities || 0} / 总配置 ${kpi.total_configs || 0} / 新增 ${kpi.new_opportunities || 0}`,
        `【平台分布】${platforms.map((p: any) => `${p.name || '未分类'}:${p.count}`).join('、') || '无数据'}`,
        `【业务排行】${topSales.map((s: any) => `${s.name}:${s.count}个`).join('、') || '无数据'}`,
      ]
      return lines.join('\n')
    } catch {
      return ''
    }
  },
}

export const contextProviders: ContextProvider[] = [
  quoteProvider,
  opportunityProvider,
  opportunityListProvider,
]

// ── 趋势分析快捷指令：动态读配置 prompt + 富上下文（调 /api/dashboard/trend-overview）──
// prompt 模板存 system_config.ai_trend_analysis（前端 AI 设置可改，反对硬编码）；
// 此处 DEFAULT 仅在配置读取失败时兜底，与后端种子内容不同（种子是富格式 8 段模板）。
const DEFAULT_TREND_PROMPT =
  '请基于当前商机线索的数据，分析本期趋势。从【增长信号】【风险预警】【行动建议】三个维度各给出 1-2 条洞察：每条要具体、带数据支撑、可操作，不要套话。'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let trendCfgCache: any = null

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function loadTrendConfig(): Promise<any> {
  if (trendCfgCache) return trendCfgCache
  try {
    const r = await fetch('/api/system-config/ai_trend_analysis/value')
    const data = await r.json()
    trendCfgCache = data.value || {}
  } catch {
    trendCfgCache = {}
  }
  return trendCfgCache
}

async function loadTrendPrompt(): Promise<string> {
  const cfg = await loadTrendConfig()
  return cfg.prompt_template || DEFAULT_TREND_PROMPT
}

// 把单周期 summary 拼成可读文本（KPI / 平台 / 机箱 / 销售TOP / 逐期时序）
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function formatPeriod(label: string, s: any): string {
  if (!s) return ''
  const kpi = s.kpi || {}
  const plats = (s.structure?.platforms || []).map((p: any) => `${p.name || '未分类'}:${p.count}`).join('、')
  const chassis = (s.structure?.chassis || []).map((c: any) => `${c.name || '未分类'}:${c.count}`).join('、')
  const top = (s.sales_rank?.top || []).map((t: any) => `${t.name}:${t.count}`).join('、')
  const series = s.charts?.chart1?.total_series || []
  const trend = series.length >= 2
    ? `逐期(${series.length}点): ${series.map((d: any) => `${d.date}:${d.value}`).join(', ')}`
    : ''
  return [
    `【${label}·${s.period_label || ''}】`,
    `商机 ${kpi.total_opportunities || 0}(新增 ${kpi.new_opportunities || 0}) / 配置 ${kpi.total_configs || 0}(新增 ${kpi.new_configs || 0})`,
    plats ? `平台: ${plats}` : '',
    chassis ? `机箱: ${chassis}` : '',
    top ? `销售TOP: ${top}` : '',
    trend,
  ].filter(Boolean).join('\n')
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function formatHighlights(hs: any[]): string {
  if (!hs || !hs.length) return ''
  const lines = hs.map((h: any) => {
    const parts = [
      h.customer_name || '未命名',
      h.platform_type,
      h.chassis_form,
      h.purchase_qty ? `${h.purchase_qty}台` : '',
      h.config_count ? `${h.config_count}配置` : '',
      h.result,
    ].filter(Boolean)
    const line = parts.join(' / ')
    return h.lost_reason ? `${line} — 丢标原因:${h.lost_reason}` : line
  })
  return `【近期重点商机(近半年,按台数降序)】\n${lines.join('\n')}`
}

async function buildTrendContext(): Promise<string> {
  const cfg = await loadTrendConfig()
  const limit = cfg.highlight_count || 10
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let data: any
  try {
    const r = await fetch(`/api/dashboard/trend-overview?limit=${limit}`)
    data = await r.json()
  } catch {
    return '【趋势数据】获取失败，请稍后重试。'
  }
  return [
    formatPeriod('本周', data.week),
    formatPeriod('本月', data.month),
    formatPeriod('近半年', data.half_year),
    formatHighlights(data.highlights),
  ].filter(Boolean).join('\n\n')
}

/**
 * 助手快捷指令 — 按当前页激活的 provider 条件渲染（providerKey 命中才显示）。
 * 点击即将 prompt 作为用户消息发出，回复经 WS 流式返回。
 * prompt 可为函数（动态读配置）、context 可为函数（自定义富上下文）；缺省走通用 provider 摘要。
 * 加新指令：追加一条并指定 providerKey，AssistantPanel 不改。
 */
export const assistantQuickActions: QuickAction[] = [
  {
    key: 'trend-analysis',
    label: '分析本期趋势',
    icon: '📈',
    providerKey: 'opportunity-list',
    prompt: loadTrendPrompt,
    context: buildTrendContext,
  },
]
