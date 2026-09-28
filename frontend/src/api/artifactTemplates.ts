/**
 * 产出物模板 API（AI办公室·产出物 tab）
 * 模板=确定性形状层（blocks），AI 只填内容；图表块引用后端 chart_assets 注册表。
 */
import axios from 'axios'

const API_BASE = '/api/artifact-templates'

export interface ArtifactBlock {
  id?: string
  type: 'title' | 'text' | 'kpi' | 'chart' | 'table'
  title?: string
  asset?: string
  source?: 'answer' | 'payload'
  key?: string
  height?: number
  params?: Record<string, unknown>
  [k: string]: unknown
}

export interface ArtifactTemplate {
  id: number
  key: string
  name: string
  format: string
  description: string
  blocks: ArtifactBlock[]
  version: number
  is_deleted: boolean
  created_at?: string
  updated_at?: string
  created_by?: string
  updated_by?: string
}

export interface ChartAssetParamSpec {
  key: string
  label: string
  default: number
  min?: number
  max?: number
  step?: number
  unit?: string
}

export interface ChartAssetMeta {
  id: string
  name: string
  kind: 'kpi' | 'chart' | 'table'
  source_page: string
  desc: string
  params?: ChartAssetParamSpec[]
}

export const artifactTemplateApi = {
  async list(): Promise<ArtifactTemplate[]> {
    const res = await axios.get(API_BASE)
    return res.data
  },

  async getById(id: number): Promise<ArtifactTemplate> {
    const res = await axios.get(`${API_BASE}/${id}`)
    return res.data
  },

  async listChartAssets(): Promise<ChartAssetMeta[]> {
    const res = await axios.get(`${API_BASE}/chart-assets`)
    return res.data
  },

  /** 预览：返回完整 HTML 文档（iframe srcdoc 消费） */
  async preview(payload: { key: string; name: string; format: string; description?: string; blocks: ArtifactBlock[] }): Promise<string> {
    const res = await axios.post(`${API_BASE}/preview`, payload, { responseType: 'text', transformResponse: [(d) => d] })
    return res.data
  },

  /** 样例 PDF：新窗口打开或下载 */
  previewPdfUrl(): string {
    return `${API_BASE}/render-sample-pdf`
  },

  async create(data: Partial<ArtifactTemplate>): Promise<ArtifactTemplate> {
    const res = await axios.post(API_BASE, data)
    return res.data
  },

  async update(id: number, data: Partial<ArtifactTemplate>): Promise<ArtifactTemplate> {
    const res = await axios.put(`${API_BASE}/${id}`, data)
    return res.data
  },

  async remove(id: number): Promise<void> {
    await axios.delete(`${API_BASE}/${id}`)
  },
}
