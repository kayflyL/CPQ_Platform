/**
 * 上下文 provider 实现 — 当前三个域:
 * - quoteProvider: 报价工作台(商机 + 当前报价单配置)
 * - opportunityProvider: 商机详情页(商机概览 + 报价单列表)
 * - opportunityListProvider: 商机线索页(驾驶舱统计 + 业务排行)
 *
 * 未来加策略中心等:在此 export 新 provider,加到 contextProviders 数组即可。
 */
import type { ContextProvider } from './assistantContext'

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
