/**
 * 规格书模板 API
 */
import axios from 'axios'
import type { SpecTemplate } from '@/types/specTemplate'

const API_BASE = '/api/spec-templates'

export const specTemplateApi = {
  /** 列表查询 */
  async list(): Promise<SpecTemplate[]> {
    const res = await axios.get(API_BASE)
    return res.data
  },

  /** 获取默认模板 */
  async getDefault(): Promise<SpecTemplate> {
    const res = await axios.get(`${API_BASE}/default`)
    return res.data
  },

  /** 获取详情 */
  async getById(id: number): Promise<SpecTemplate> {
    const res = await axios.get(`${API_BASE}/${id}`)
    return res.data
  },

  /** 创建模板 */
  async create(data: Partial<SpecTemplate>): Promise<SpecTemplate> {
    const res = await axios.post(API_BASE, data)
    return res.data
  },

  /** 更新模板 */
  async update(id: number, data: Partial<SpecTemplate>): Promise<SpecTemplate> {
    const res = await axios.put(`${API_BASE}/${id}`, data)
    return res.data
  },

  /** 删除模板 */
  async delete(id: number): Promise<void> {
    await axios.delete(`${API_BASE}/${id}`)
  },

  /** 设为默认 */
  async setDefault(id: number): Promise<void> {
    await axios.post(`${API_BASE}/${id}/set-default`)
  },

  /** 复制模板 */
  async copy(id: number): Promise<SpecTemplate> {
    const res = await axios.post(`${API_BASE}/${id}/copy`)
    return res.data
  },

  /** 上传 Logo */
  async uploadLogo(file: File): Promise<{ url: string; filename: string }> {
    const fd = new FormData()
    fd.append('file', file)
    const res = await axios.post(`${API_BASE}/upload-logo`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return res.data
  },

  /** 获取预览数据 */
  async getPreviewData(opportunityId: string, quotationId?: string): Promise<any> {
    const params: any = { opportunity_id: opportunityId }
    if (quotationId) params.quotation_id = quotationId
    const res = await axios.get(`${API_BASE}/preview-data`, { params })
    return res.data
  }
}
