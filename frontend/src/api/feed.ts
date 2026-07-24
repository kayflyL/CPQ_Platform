/**
 * Feed API client — unified collaboration stream (messages + attachments).
 * Replaces the old OpportunityFiles.vue + CommentPanel.vue split.
 *
 * A dedicated axios instance injects X-User-Id from the persisted current-user
 * picker so every feed request is attributed. Swap point for JWT later.
 */
import axios from 'axios'
import type { AxiosInstance } from 'axios'

// ── types ──
export interface FeedUser {
  user_id: string
  name: string
  email?: string
  role?: string
  created_at?: string
}
export interface FeedAttachment {
  attachment_id: string
  opportunity_id: string
  message_id?: string
  uploader_user_id: string
  uploader_name: string
  original_filename: string
  storage_key: string
  file_size: number
  mime_type: string
  kind: string
  category?: string
  quotation_id?: string
  version: number
  version_group: string
  created_at: string
  deleted_at?: string
}
export interface FeedMessage {
  message_id: string
  opportunity_id: string
  author_user_id: string
  author_name: string
  body: string
  kind: string
  quotation_id?: string
  created_at: string
  updated_at?: string
  deleted_at?: string
  attachments: FeedAttachment[]
}

// ── http instance with current-user header ──
const http: AxiosInstance = axios.create({ baseURL: '', timeout: 60000 })
http.interceptors.request.use((config) => {
  const u = getCurrentUser()
  if (u?.user_id) config.headers['X-User-Id'] = u.user_id
  return config
})

const STORAGE_KEY = 'cpq_feed_current_user'
export function getCurrentUser(): FeedUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as FeedUser) : null
  } catch {
    return null
  }
}
export function setCurrentUser(u: FeedUser) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(u))
}

// ── API ──
export const feedApi = {
  users: {
    list: () => http.get<FeedUser[]>('/api/feed/users').then((r) => r.data),
    ensure: (name: string, email?: string) =>
      http.post<FeedUser>('/api/feed/users', { name, email }).then((r) => r.data),
  },
  messages: {
    list: (oppId: string) =>
      http.get<{ messages: FeedMessage[] }>(`/api/feed/${oppId}/messages`).then((r) => r.data.messages),
    /** Post a message with optional attachments. */
    create: (oppId: string, body: string, files: File[] = []) => {
      const fd = new FormData()
      fd.append('body', body)
      files.forEach((f) => fd.append('files', f))
      return http
        .post<{ message: FeedMessage }>(`/api/feed/${oppId}/messages`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data.message)
    },
    remove: (id: string) => http.delete(`/api/feed/messages/${id}`),
  },
  attachments: {
    list: (oppId: string) =>
      http.get<{ attachments: FeedAttachment[] }>(`/api/feed/${oppId}/attachments`).then((r) => r.data.attachments),
    upload: (oppId: string, file: File, opts?: { category?: string; quotation_id?: string; kind?: string }) => {
      const fd = new FormData()
      fd.append('file', file)
      if (opts?.category) fd.append('category', opts.category)
      if (opts?.quotation_id) fd.append('quotation_id', opts.quotation_id)
      if (opts?.kind) fd.append('kind', opts.kind)
      return http
        .post<{ attachment: FeedAttachment }>(`/api/feed/${oppId}/attachments`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data.attachment)
    },
    downloadUrl: (id: string) => `/api/feed/attachments/${id}/download`,
    remove: (id: string) => http.delete(`/api/feed/attachments/${id}`),
    updateCategory: (id: string, category: string | null) =>
      http
        .patch<{ attachment: FeedAttachment }>(`/api/feed/attachments/${id}/category`, { category })
        .then((r) => r.data.attachment),
    versions: (id: string) =>
      http.get<{ versions: FeedAttachment[]; current: FeedAttachment }>(`/api/feed/attachments/${id}/versions`).then((r) => r.data),
    addVersion: (id: string, file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return http
        .post<{ attachment: FeedAttachment }>(`/api/feed/attachments/${id}/version`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data.attachment)
    },
  },
}
