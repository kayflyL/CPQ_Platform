/**
 * Univer 导出模板类型定义（全新，与旧 template.ts 完全独立）
 */

/** 静态绑定 */
export interface StaticBinding {
  id: string
  sheetId: string
  cellAddress: string  // 如 "B3"
  fieldKey: string     // 如 "customer_name"
  dataType: 'static'
}

/** 动态绑定 */
export interface DynamicBinding {
  id: string
  sheetId: string
  cellAddress: string  // 起始单元格，如 "A5"
  fieldKey: string     // 区域标识，如 "l6_details"
  dataType: 'dynamic'
  
  regionFieldKey: string    // 数据源区域
  templateRow: number       // 样式模板行号（1-indexed）
  fieldMapping: Record<string, string>  // 字段 → 列字母
  
  descriptionTemplate?: string
  descriptionSeparator?: string
}

export type Binding = StaticBinding | DynamicBinding

/** Sheet 配置 */
export interface SheetConfig {
  cover?: {
    sheetId: string
  }
  config?: {
    sheetId: string | null
    nameTemplate?: string
    splitByConfig?: boolean
  }
}

/** Univer 导出模板 */
export interface UniverTemplate {
  id: number
  name: string
  display_name: string
  is_default: boolean
  workbook_snapshot?: Record<string, any>  // 列表接口不含，详情接口含
  bindings: Binding[]
  sheet_config: SheetConfig
  created_at: string
  updated_at: string
}

/**
 * 业务字段定义
 */
export interface BusinessField {
  key: string
  label: string
  category: 'opportunity' | 'config' | 'system'
  description?: string
}

/** 预览数据源 */
export interface PreviewData {
  customer_name?: string
  opportunity_name?: string
  platform_type?: string
  total_qty?: number
  l6_details?: any[]
  kp_details?: any[]
  warranty_details?: any[]
  config_summary?: any[]
  [key: string]: any
}
