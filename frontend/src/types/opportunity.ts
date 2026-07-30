/**
 * Project and Quotation type definitions
 */

export interface Project {
  opportunity_id: string
  customer_name: string
  status: string
  created_at: string
  updated_at: string
  
  // Project-level metadata (user-editable)
  purchase_qty: number
  platform_type: string
  chassis_form: string
  sales_person: string
  fae: string
  // 商机上下文（pricing scope 维度，可选 — 后端 extra_fields 动态字段）
  customer_type?: string
  // 业务结果流转（与 status 正交）
  result?: 'pending' | 'won' | 'lost'

  // Computed fields from latest quotation
  quotation_count: number
  config_count: number
}

export interface Quotation {
  quotation_id: string
  opportunity_id: string
  version: string
  quotation_name: string
  file_path?: string

  // Quotation-level fields (user-editable)
  quotation_date: string

  // Computed totals
  l6_price: number
  total_qty: number
  config_count: number
  total_price: number
  profit_margin: number

  created_at: string
  updated_at: string
  status: string
  // 草稿/已导出状态机：NULL=草稿(可进工作台)；非空=已导出冻结(时间戳，点列表只看 Excel+成本)
  exported_at?: string | null
  cost_snapshot?: Record<string, any> | null
  // 列表轻量标志（list 端点剥离完整 snapshot，留布尔供行内判断）
  has_cost_snapshot?: boolean
  // 手工补录过（manual:true，未冻结）→ 列表给「编辑成本」入口可二次进抽屉改
  has_manual_cost?: boolean

  // WIP fields (primary-quotation flag + platform classification)
  is_primary?: boolean
  platform_type?: string
}

// Alias: Project is being renamed to Opportunity (商机) across the UI.
// Kept as a type alias so views can use the semantically-correct name
// without duplicating the shape.
export type Opportunity = Project

export interface ProjectItem {
  item_id?: number
  quotation_id: string
  config_name: string
  category: string
  catalogue: string
  description: string
  part_category: string
  qty: number
  base_price: number
  final_price: number
  profit_margin: number
}

export interface ProjectListResponse {
  items: Project[]
  total: number
}

export interface QuotationListResponse {
  quotations: Quotation[]
}
