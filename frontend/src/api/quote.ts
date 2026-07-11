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

// Parse quotation preview (without creating quotation record)
export async function parseQuotationPreview(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post('/quote/parse-preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return response.data
}

// Confirm upload and create quotation record
export async function confirmQuotationUpload(file: File, opportunityId: string) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('opportunity_id', opportunityId)
  const response = await api.post('/quote/confirm-upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return response.data
}

// Update quotation L6 record (manual selection)
export async function updateQuotationL6(quotationId: string, l6Record: any) {
  const response = await api.patch(`/quotations/${quotationId}/l6`, l6Record)
  return response.data
}

// Get L6 candidates (top 3 by match score)
export async function getL6Candidates(params: {
  chassis?: string
  model?: string
  drive_bays?: string
  psu?: string
  motherboard?: string
}) {
  const response = await api.get('/quote/l6/candidates', { params })
  return response.data
}

export async function saveProject(data: any) {
  return api.post('/opportunities', data)
}