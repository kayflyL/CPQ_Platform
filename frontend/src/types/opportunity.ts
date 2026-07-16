/**
 * Project and Quotation type definitions
 */

export interface Project {
  project_id: string
  folder_name?: string
  project_name: string
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
  
  // Computed fields from latest quotation
  quotation_count: number
  config_count: number
}

export interface Quotation {
  quotation_id: string
  project_id: string
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
}

export interface ProjectItem {
  item_id?: number
  quotation_id: string
  config_name: string
  category: string
  part_name: string
  spec: string
  qty: number
  confirmed_price: number
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
