/**
 * 通知类型元数据 SSOT — 铃铛 popover 与通知中心页共用。
 * icon 色用语义色 class（i-blue 等），色值 SSOT = tokens.css 的 --cpq-notif-*（双主题）。
 * 分组：待办（需我做事）/ 审批（撤回+毛利审批全周期）/ 动态（进展知会）。
 */
import {
  ArrowRightOutlined,
  AuditOutlined,
  FileDoneOutlined,
  RollbackOutlined,
  RedoOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import type { FunctionalComponent } from 'vue'

export interface NotificationTypeMeta {
  label: string
  /** 筛选分组键 */
  group: NotificationGroupKey
  icon: FunctionalComponent
  colorClass: string
}

export type NotificationGroupKey = 'todo' | 'approval' | 'activity'

export const NOTIFICATION_GROUPS: { key: NotificationGroupKey; label: string; types: string[] }[] = [
  { key: 'todo', label: '待办', types: ['task_assigned', 'card_returned'] },
  {
    key: 'approval',
    label: '审批',
    types: ['withdraw_requested', 'withdraw_approved', 'withdraw_rejected', 'pricing_approval_requested', 'pricing_approval_decided'],
  },
  { key: 'activity', label: '动态', types: ['stage_advanced', 'quote_submitted'] },
]

const META: Record<string, NotificationTypeMeta> = {
  task_assigned: { label: '任务', group: 'todo', icon: UserAddOutlined, colorClass: 'i-blue' },
  stage_advanced: { label: '阶段', group: 'activity', icon: ArrowRightOutlined, colorClass: 'i-green' },
  card_returned: { label: '退回', group: 'todo', icon: RollbackOutlined, colorClass: 'i-red' },
  withdraw_requested: { label: '撤回', group: 'approval', icon: RedoOutlined, colorClass: 'i-violet' },
  withdraw_approved: { label: '撤回', group: 'approval', icon: RedoOutlined, colorClass: 'i-violet' },
  withdraw_rejected: { label: '撤回', group: 'approval', icon: RedoOutlined, colorClass: 'i-violet' },
  quote_submitted: { label: '报价', group: 'activity', icon: FileDoneOutlined, colorClass: 'i-cyan' },
  pricing_approval_requested: { label: '毛利审批', group: 'approval', icon: AuditOutlined, colorClass: 'i-amber' },
  pricing_approval_decided: { label: '毛利审批', group: 'approval', icon: AuditOutlined, colorClass: 'i-amber' },
}

const FALLBACK: NotificationTypeMeta = { label: '通知', group: 'activity', icon: ArrowRightOutlined, colorClass: 'i-blue' }

export function notificationMeta(type: string): NotificationTypeMeta {
  return META[type] || FALLBACK
}

/** 分组未读数：后端 by_type(type→count) 求和成 group→count */
export function groupUnread(byType: Record<string, number>): Record<NotificationGroupKey, number> {
  const out = {} as Record<NotificationGroupKey, number>
  for (const g of NOTIFICATION_GROUPS) {
    out[g.key] = g.types.reduce((sum, t) => sum + (byType[t] || 0), 0)
  }
  return out
}
