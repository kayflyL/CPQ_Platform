/**
 * 聊天时间显示（会话列表/消息 meta 共用）：
 * 当天=HH:MM，昨天=「昨天」，今年=MM-DD，更早=YYYY-MM-DD。
 * 后端 now_iso 为本地 "YYYY-MM-DD HH:MM:SS"，new Date 需把空格换 T。
 */
export function fmtChatTime(raw?: string | null): string {
  const s = String(raw || '').trim()
  if (!s) return ''
  const d = new Date(s.includes('T') ? s : s.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  if (sameDay) return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const yest = new Date(now.getTime() - 86400000)
  const isYest = d.getFullYear() === yest.getFullYear() && d.getMonth() === yest.getMonth() && d.getDate() === yest.getDate()
  if (isYest) return '昨天'
  if (d.getFullYear() === now.getFullYear()) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
