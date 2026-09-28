/** 相对时间：刚刚 / N分钟前 / N小时前 / 昨天 HH:mm / MM-DD HH:mm / YYYY-MM-DD */
export function formatRelativeTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  if (diffMs < 60_000) return '刚刚'
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)} 分钟前`
  const sameDay = d.toDateString() === now.toDateString()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (sameDay) return `${Math.floor(diffMs / 3_600_000)} 小时前`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${hm}`
  const md = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  if (d.getFullYear() === now.getFullYear()) return `${md} ${hm}`
  return `${d.getFullYear()}-${md}`
}

/** 通知中心按天分组标签：今天 / 昨天 / 更早（本月内带日期） */
export function dayGroupLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '更早'
  const now = new Date()
  if (d.toDateString() === now.toDateString()) return '今天'
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return '昨天'
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月`
}
