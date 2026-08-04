/**
 * BOM案例库 API（/api/bom-cases）—— 选型配置 · BOM案例库。
 * 无数字 id：case_key 为时间戳型业务键（BC-YYYYMMDD-HHMMSS-ffffff）；
 * kp_lines 只存 [{part_id, qty, hint?}] 引用 kp_parts（单一真源），详情返回解析后的 name/category/最新价。
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface BomKpLine {
  part_id: number | null
  qty: number
  hint?: string
  name?: string
  pn?: string
  category?: string
  unit_price?: number
  unresolved?: boolean
}

/** 报价工作台 BomTable 可直接渲染的行（L6 段 + KP 段，同 bom_excel_rows 结构） */
export interface BomExcelRow {
  category: string          // L6 / Key Parts
  part_category?: string
  catalogue: string
  description: string
  qty: number
  base_price?: number
  currency?: string
}

/** L6 配置单快照行（保存时固化，案例自包含；技术员 excel 样式 Catalogue/Description/Qty） */
export interface L6Row { catalogue: string; description: string; qty: number }

export interface BomCase {
  case_key: string
  name: string
  scenario_tags: string[]
  model_id: number | null
  base_config_id: number | null
  bom_template_id: number | null
  model_name?: string
  base_config_name?: string
  base_config_desc?: string
  bom_template_name?: string
  requirement?: string
  l6_config_desc?: string
  server_type?: string
  series?: string
  bom_excel_rows?: BomExcelRow[]
  l6_rows?: L6Row[]
  chassis_signals: Record<string, any>
  kp_lines: BomKpLine[]
  price_snapshot: Record<string, any>
  notes?: string
  version: number
  enabled: boolean
  created_at: string | null
  updated_at: string | null
  created_by: string
  updated_by: string
}

export interface KpCategory { id: number; name: string }
export interface KpPart {
  id: number
  pn: string
  name: string
  category: string
  brand: string | null
  unit_price: number
}

export const bomCaseApi = {
  list: (params?: { tag?: string; q?: string; enabled?: boolean; with_parts?: boolean }) =>
    RESP<{ cases: BomCase[] }>(axios.get('/api/bom-cases/', { params })),
  get: (case_key: string) => RESP<BomCase>(axios.get(`/api/bom-cases/${encodeURIComponent(case_key)}`)),
  create: (data: Partial<BomCase>) => RESP<BomCase>(axios.post('/api/bom-cases/', data)),
  update: (case_key: string, data: Partial<BomCase>) => RESP<BomCase>(axios.put(`/api/bom-cases/${encodeURIComponent(case_key)}`, data)),
  remove: (case_key: string) => RESP<{ success: boolean }>(axios.delete(`/api/bom-cases/${encodeURIComponent(case_key)}`)),
  /** 按 BOM 模板求值 L6 配置单行（编辑器选基准配置/模板时调用） */
  l6Preview: (data: { base_config_id: number; bom_template_id: number; kp_lines?: BomKpLine[]; chassis_signals?: Record<string, any> }) =>
    RESP<{ rows: L6Row[] }>(axios.post('/api/bom-cases/l6-preview', data)),
}

/** KP 料号目录（供案例 KP 行选件；单一真源 kp.kp_parts） */
export const kpCatalogApi = {
  categories: () => RESP<KpCategory[]>(axios.get('/api/kp/categories')),
  parts: (category_id?: number, series?: string) =>
    RESP<KpPart[]>(axios.get('/api/kp/parts', { params: { category_id, series } })),
}
