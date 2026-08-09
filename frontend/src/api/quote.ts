import axios from 'axios'
import { AUTH_TOKEN_KEY } from './auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})
// Bearer token：服务端按 JWT 解析上传/归档的归属用户。
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
// Upload quotation to a specific opportunity (creates quotation record + archives source file)
export async function uploadQuotationToProject(file: File, opportunityId: string) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('opportunity_id', opportunityId)
  const response = await api.post('/quote/upload-to-opportunity', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return response.data
}

export async function saveProject(data: any) {
  return api.post('/opportunities', data)
}

// KP 价格历史（某型号）
export async function getKpHistory(model: string) {
  const r = await api.get('/quote/kp/history', { params: { model } })
  return r.data
}

// KP 单条手动同步：把当前 KP 配件价格写入配件库历史（替代保存时自动批量同步）
export async function syncKpPrice(payload: { category: string; model: string; price: number; currency?: string; note?: string }) {
  const r = await api.post('/quote/kp/sync-price', {
    category: payload.category,
    model: payload.model,
    price: payload.price,
    currency: payload.currency || 'RMB',
    note: payload.note || '报价工作台手动同步',
  })
  return r.data
}