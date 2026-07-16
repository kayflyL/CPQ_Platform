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