import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})
// Quote API (legacy upload)
export async function uploadQuotation(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post('/quote/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return response.data
}

// Upload quotation to a specific opportunity (creates quotation record)
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