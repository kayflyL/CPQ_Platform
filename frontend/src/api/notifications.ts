/**
 * 站内通知 API client — 收件箱 REST。
 * WS 实时推送走 useNotifications composable（/api/notifications/ws）。
 */
import axios from 'axios'
import type { AxiosInstance } from 'axios'
import { AUTH_TOKEN_KEY } from './auth'

export interface AppNotification {
  notification_id: string
  user_id: string
  type: string
  title: string
  body: string
  opportunity_id: string
  payload: Record<string, any> | null
  read_at: string | null
  created_at: string
}

const http: AxiosInstance = axios.create({ baseURL: '', timeout: 30000 })
http.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export const notificationsApi = {
  async list(page = 1, pageSize = 20, unreadOnly = false, types?: string[]): Promise<{ notifications: AppNotification[]; total: number }> {
    const { data } = await http.get('/api/notifications', {
      params: { page, page_size: pageSize, unread_only: unreadOnly, types: types?.length ? types.join(',') : undefined },
    })
    return data
  },
  async unreadCount(): Promise<number> {
    const { data } = await http.get('/api/notifications/unread-count')
    return data?.count ?? 0
  },
  async unreadStats(): Promise<{ count: number; byType: Record<string, number> }> {
    const { data } = await http.get('/api/notifications/unread-count')
    return { count: data?.count ?? 0, byType: data?.by_type ?? {} }
  },
  async markRead(notificationId: string): Promise<number> {
    const { data } = await http.post(`/api/notifications/${encodeURIComponent(notificationId)}/read`)
    return data?.count ?? 0
  },
  async markAllRead(): Promise<number> {
    const { data } = await http.post('/api/notifications/read-all')
    return data?.marked ?? 0
  },
  async remove(notificationId: string): Promise<number> {
    const { data } = await http.delete(`/api/notifications/${encodeURIComponent(notificationId)}`)
    return data?.count ?? 0
  },
  async clearRead(): Promise<number> {
    const { data } = await http.post('/api/notifications/clear-read')
    return data?.deleted ?? 0
  },
}
