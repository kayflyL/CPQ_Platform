/**
 * Feed API client — unified collaboration stream (messages + attachments).
 * Replaces the old OpportunityFiles.vue + CommentPanel.vue split.
 *
 * A dedicated axios instance attaches the Bearer token so every feed request
 * is attributed to the logged-in user (backend resolves identity from JWT).
 */
import axios from 'axios'
import type { AxiosInstance } from 'axios'
import { AUTH_TOKEN_KEY } from './auth'

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
  flow_card_id?: number | null
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
  node_key?: string
  flow_card_id?: number | null
  created_at: string
  updated_at?: string
  deleted_at?: string
  attachments: FeedAttachment[]
}

// ── http instance with Bearer token（服务端按 JWT 解析身份）──
const http: AxiosInstance = axios.create({ baseURL: '', timeout: 60000 })
http.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── API ──
export const feedApi = {
  messages: {
    list: (oppId: string) =>
      http.get<{ messages: FeedMessage[] }>(`/api/feed/${oppId}/messages`).then((r) => r.data.messages),
    /** Post a message with optional attachments. */
    create: (oppId: string, body: string, files: File[] = [], nodeKey?: string, flowCardId?: number | null) => {
      const fd = new FormData()
      fd.append('body', body)
      if (nodeKey) fd.append('node_key', nodeKey)
      if (flowCardId) fd.append('flow_card_id', String(flowCardId))
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
    upload: (oppId: string, file: File, opts?: { category?: string; quotation_id?: string; kind?: string; flow_card_id?: number | null }) => {
      const fd = new FormData()
      fd.append('file', file)
      if (opts?.category) fd.append('category', opts.category)
      if (opts?.quotation_id) fd.append('quotation_id', opts.quotation_id)
      if (opts?.kind) fd.append('kind', opts.kind)
      if (opts?.flow_card_id) fd.append('flow_card_id', String(opts.flow_card_id))
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
