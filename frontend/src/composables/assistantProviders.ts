/**
 * 上下文 provider 实现 — 当前两个域:
 * - quoteProvider: 报价工作台(商机 + 当前报价单配置)
 * - opportunityProvider: 商机详情页(商机概览 + 报价单列表)
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

export const contextProviders: ContextProvider[] = [quoteProvider, opportunityProvider]
