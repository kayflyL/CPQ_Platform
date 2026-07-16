/**
 * Univer 导出模板 API（全新，与旧 template.ts 完全独立）
 */
import axios from 'axios'
import type { UniverTemplate, Binding, SheetConfig } from '@/types/univerTemplate'

const API_BASE = '/api/univer-templates'

export const univerTemplateApi = {
  /** 列表查询（不含 workbook_snapshot） */
  async list(): Promise<UniverTemplate[]> {
    const resp = await axios.get(API_BASE)
    return resp.data
  },

  /** 详情查询（含完整 snapshot） */
  async getById(id: number): Promise<UniverTemplate> {
    const resp = await axios.get(`${API_BASE}/${id}`)
    return resp.data
  },

  /** 创建模板 */
  async create(data: {
    name: string
    display_name: string
    is_default?: boolean
    workbook_snapshot: Record<string, any>
    bindings?: Binding[]
    sheet_config?: SheetConfig
  }): Promise<UniverTemplate> {
    const resp = await axios.post(API_BASE, data)
    return resp.data
  },

  /** 更新模板 */
  async update(
    id: number,
    data: {
      name?: string
      display_name?: string
      is_default?: boolean
      workbook_snapshot?: Record<string, any>
      bindings?: Binding[]
      sheet_config?: SheetConfig
    }
  ): Promise<UniverTemplate> {
    const resp = await axios.put(`${API_BASE}/${id}`, data)
    return resp.data
  },

  /** 删除模板 */
  async delete(id: number): Promise<void> {
    await axios.delete(`${API_BASE}/${id}`)
  },

  /** 设为默认 */
  async setDefault(id: number): Promise<void> {
    await axios.post(`${API_BASE}/${id}/set-default`)
  },

  /** 上传 Excel → 转为 Univer 格式 */
  async uploadExcel(file: File): Promise<{
    workbook_snapshot: Record<string, any>
    sheet_config: SheetConfig
    original_filename: string
  }> {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await axios.post(`${API_BASE}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return resp.data
  },

  /** 预览（填充数据后返回 snapshot） */
  async preview(
    templateId: number,
    opportunityId: string,
    quotationId?: string,
    bindings?: Binding[]
  ): Promise<{
    workbook_snapshot: Record<string, any>
    binding_count: number
    data_summary: {
      static_fields: number
      dynamic_regions: number
    }
  }> {
    const params: Record<string, string> = { opportunity_id: opportunityId }
    if (quotationId) {
      params.quotation_id = quotationId
    }
    const resp = await axios.post(`${API_BASE}/${templateId}/preview`, { bindings }, { params })
    return resp.data
  },

  /** 导出 Excel */
  async export(
    templateId: number,
    opportunityId: string,
    quotationId?: string
  ): Promise<Blob> {
    const params: Record<string, string> = { opportunity_id: opportunityId }
    if (quotationId) {
      params.quotation_id = quotationId
    }
    const resp = await axios.get(`${API_BASE}/${templateId}/export`, {
      params,
      responseType: 'blob',
    })
    return resp.data
  },
}
