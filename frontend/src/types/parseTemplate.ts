/**
 * 解析模板类型定义
 * 混合模型：静态字段用CellBinding，动态区域用关键词定位
 */
import type { CellBinding } from './template'

/** 解析模板 */
export interface ParseTemplate {
  id: string
  name: string
  description?: string
  createdAt: number
  
  /** 静态字段绑定（CellBinding） */
  staticBindings: CellBinding[]
  
  /** 动态区域配置（关键词定位） */
  dynamicRegions: DynamicRegion[]
}

/** 动态区域配置 */
export interface DynamicRegion {
  id: string
  /** 区域名称，如"L6配件"、"KP配件" */
  name: string
  /** 区域类型 */
  regionType: 'l6' | 'kp' | 'custom'
  
  /** 业务字段 key（供导出模板引用） */
  fieldKey: string
  /** 业务字段标签（显示名称） */
  fieldLabel: string
  
  /** 起始关键词（逗号分隔，如"L6"） */
  startKeywords: string
  /** 结束关键词（逗号分隔，如"Keyparts,KP"） */
  endKeywords: string
  
  /** 解析时的列映射：字段名 → 列字母 */
  fieldMapping: Record<string, string>
}

/** 解析结果 */
export interface ParsedResult {
  /** 静态字段数据 */
  staticData: Record<string, string | number | null>
  /** 动态区域数据：regionName → rows */
  dynamicData: Record<string, ParsedRow[]>
  /** 解析警告信息 */
  warnings: string[]
}

/** 解析出的行数据 */
export interface ParsedRow {
  [fieldKey: string]: string | number | null
}

/** 解析模板Store状态 */
export interface ParseTemplateState {
  /** 已保存的模板列表 */
  templates: ParseTemplate[]
  /** 当前编辑的模板 */
  currentTemplate: ParseTemplate | null
  /** 解析结果 */
  parsedResult: ParsedResult | null
  /** 是否正在解析 */
  parsing: boolean
}
