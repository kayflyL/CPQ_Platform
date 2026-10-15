/**
 * 产出物模板 API（AI办公室·产出物 tab）
 * 模板=确定性形状层（blocks），AI 只填内容；图表块引用后端 chart_assets 注册表。
 */
import axios from 'axios'

const API_BASE = '/api/artifact-templates'

export interface KpiMetricOption {
  key: string
  label: string
  unit?: string
}

/** kpi 区块的指标构成（key=目录原子；label=显示名覆盖；数组序=渲染序） */
export interface KpiMetricPick {
  key: string
  label?: string
}

export interface ArtifactBlock {
  id?: string
  type:
    | 'title' | 'text' | 'kpi' | 'chart' | 'table' | 'fields'
    | 'heading' | 'callout' | 'divider' | 'image'
  title?: string
  asset?: string
  source?: 'answer' | 'payload' | 'literal'
  key?: string
  height?: number
  params?: Record<string, unknown>
  /** 12 列栅格宽（4/6/8/12），缺省=整行 */
  span?: number
  /** text/callout：模板自写静态文案（markdown 子集） */
  text?: string
  /** title 区块：钉固定文案（留空回落 meta） */
  subtitle?: string
  brand_name?: string
  brand_tag?: string
  /** title 区块：抬头公司 Logo（/api/artifact-templates/logo/x.png，上传端点返回） */
  logo_url?: string
  /** kpi 区块：指标构成 */
  metrics?: KpiMetricPick[]
  /** callout：色调与标题 */
  tone?: 'blue' | 'green' | 'amber'
  co_title?: string
  /** image：图片地址（上传端点产物路径或外链） */
  src?: string
  /** title 块：品牌色（#RGB/#RRGGBB），渲染端注入 --rpt-accent */
  accent?: string
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
  /** kpi 资产带指标原子目录（编辑器指标勾选数据源） */
  metrics?: KpiMetricOption[]
}

export interface DocContractSection {
  key: string
  title: string
}

/** 文档卡契约（扫活跃推理流节点配置聚合；章节键下拉/对账/AI 生成共用） */
export interface DocContract {
  flow_key: string
  flow_name: string
  node_key: string
  doc_name: string
  data_range: Record<string, unknown>
  sections: DocContractSection[]
}

export interface GenerateReport {
  dropped: string[]
  fixed: string[]
  added: string[]
}

export interface GenerateTraceStep {
  key: string
  title: string
  /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
  items: any
}

export interface GenerateResult {
  blocks: ArtifactBlock[]
  trace: { steps: GenerateTraceStep[] }
  provenance: { type: string; asset: string; chapter: string; cite: string }[]
  dropped: string[]
  contract: DocContract
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

  async listContracts(): Promise<DocContract[]> {
    const res = await axios.get(`${API_BASE}/contracts`)
    return res.data
  },

  /** 按契约对账补齐（确定性）：缺槽追加，未知 key 只报不删 */
  async reconcile(payload: { blocks: ArtifactBlock[]; flow_key: string; doc_name?: string }): Promise<{
    blocks: ArtifactBlock[]
    missing_added: string[]
    unknown_keys: string[]
  }> {
    const res = await axios.post(`${API_BASE}/reconcile`, payload)
    return res.data
  },

  /** AI 生成模板骨架（过程可见）：返回六步 trace + blocks；确定性校验兜底；不自动保存 */
  async generate(payload: { flow_key: string; doc_name?: string }): Promise<GenerateResult> {
    const res = await axios.post(`${API_BASE}/generate`, payload)
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
