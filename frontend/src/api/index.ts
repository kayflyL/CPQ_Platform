import axios from 'axios'
import type { Opportunity, Quotation } from '@/types/opportunity'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// Admin API
export const getMetadataFields = async (): Promise<string[]> => {
  const response = await api.get('/admin/metadata-fields')
  return response.data.fields
}

// Project API (mapped to /opportunities backend routes)
export const projectApi = {
  list: async (params?: { page?: number; page_size?: number; search?: string; include_deleted?: boolean }) => {
    const response = await api.get('/opportunities/list', { params })
    return response.data
  },
  
  getById: async (projectId: string) => {
    const response = await api.get(`/opportunities/${projectId}`)
    return response.data
  },
  
  create: async (data: { project_name: string; customer_name?: string }) => {
    const response = await api.post('/opportunities', data)
    return response.data
  },
  
  update: async (projectId: string, data: { 
    project_name?: string
    customer_name?: string
    purchase_qty?: number
    platform_type?: string
    chassis_form?: string
    sales_person?: string
    fae?: string
    quotation_person?: string
  }) => {
    const response = await api.put(`/opportunities/${projectId}`, data)
    return response.data
  },
  
  updateMeta: async (projectId: string, data: Record<string, any>) => {
    const response = await api.put(`/opportunities/${projectId}/meta`, data)
    return response.data
  },
  
  delete: async (projectId: string) => {
    const response = await api.delete(`/opportunities/${projectId}`)
    return response.data
  },
  
  trash: async (projectId: string) => {
    const response = await api.post(`/opportunities/${projectId}/trash`)
    return response.data
  },
  
  restore: async (projectId: string) => {
    const response = await api.post(`/opportunities/${projectId}/restore`)
    return response.data
  },
  
  save: async (data: any) => {
    const response = await api.post('/opportunities/save', data)
    return response.data
  },
  
  export: async (projectId: string, templateId?: string) => {
    const response = await api.post(`/opportunities/${projectId}/export`, null, {
      responseType: 'blob',
      params: templateId ? { template_id: templateId } : {}
    })
    
    // Use filename from backend Content-Disposition, fall back to projectId
    const disposition = response.headers['content-disposition'] || ''
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="?([^";]+)"?/i)
    const fileName = match ? decodeURIComponent(match[1]) : `${projectId}_报价单.xlsx`

    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', fileName)
    document.body.appendChild(link)
    link.click()
    link.remove()
  },
  
  preview: async (projectId: string, templateId?: string) => {
    const response = await api.post(`/opportunities/${projectId}/preview`, null, {
      responseType: 'blob',
      params: templateId ? { template_id: templateId } : {}
    })
    return response.data
  },

  previewJson: async (projectId: string, templateId?: string) => {
    const response = await api.post(`/opportunities/${projectId}/preview-json`, null, {
      params: templateId ? { template_id: templateId } : {}
    })
    return response.data
  },
  
  // Batch operations
  batchTrash: async (projectIds: string[]) => {
    const response = await api.post('/opportunities/batch-trash', { project_ids: projectIds })
    return response.data
  },
  
  batchRestore: async (projectIds: string[]) => {
    const response = await api.post('/opportunities/batch-restore', { project_ids: projectIds })
    return response.data
  },
  
  batchPermanentDelete: async (projectIds: string[]) => {
    const response = await api.post('/opportunities/batch-permanent-delete', { project_ids: projectIds })
    return response.data
  }
}

// Quotation API
export const quotationApi = {
  getByOpportunity: async (opportunityId: string) => {
    const response = await api.get('/quotations', { params: { opportunity_id: opportunityId } })
    return response.data.quotations || []
  },
  
  list: async (opportunityId: string, params?: { include_deleted?: boolean }) => {
    const response = await api.get('/quotations', { params: { opportunity_id: opportunityId, ...params } })
    return response.data.quotations || []
  },
  
  getById: async (quotationId: string) => {
    const response = await api.get(`/quotations/${quotationId}`)
    return response.data
  },
  
  create: async (data: { 
    project_id: string
    file_path?: string
    model_name?: string
    platform_type?: string
    chassis_form?: string
    fae?: string
    sales_person?: string
    l6_spec?: string
    quotation_name?: string
  }) => {
    const response = await api.post('/quotations', data)
    return response.data
  },
  
  update: async (quotationId: string, data: any) => {
    const response = await api.put(`/quotations/${quotationId}`, data)
    return response.data
  },
  
  rename: async (quotationId: string, quotationName: string) => {
    const response = await api.put(`/quotations/${quotationId}`, { quotation_name: quotationName })
    return response.data
  },
  
  delete: async (quotationId: string) => {
    const response = await api.delete(`/quotations/${quotationId}`)
    return response.data
  },
  
  restore: async (quotationId: string) => {
    const response = await api.post(`/quotations/${quotationId}/restore`)
    return response.data
  },
  
  saveItems: async (quotationId: string, items: any[]) => {
    const response = await api.post(`/quotations/${quotationId}/items`, items)
    return response.data
  },

  updateDetails: async (quotationId: string, data: Record<string, unknown>) => {
    const response = await api.post(`/quotations/${quotationId}/items`, data)
    return response.data
  },
  
  batchDelete: async (quotationIds: string[]) => {
    const response = await api.post('/quotations/batch-delete', { quotation_ids: quotationIds })
    return response.data
  },
  
  batchRestore: async (quotationIds: string[]) => {
    const response = await api.post('/quotations/batch-restore', { quotation_ids: quotationIds })
    return response.data
  },
  
  batchPermanentDelete: async (quotationIds: string[]) => {
    const response = await api.post('/quotations/batch-permanent-delete', { quotation_ids: quotationIds })
    return response.data
  }
}

// Export Template API (removed - template config system deleted)

export async function getExportCategories() {
  const response = await api.get('/rules/export-categories')
  return response.data
}

// Export Template API (removed - template config system deleted)


// Aliases for store/quote.ts compatibility
export const saveProject = projectApi.save
export const exportProject = projectApi.export
