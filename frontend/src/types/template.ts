/**
 * Excel 模板编辑器类型定义
 */

/** 单元格样式 */
export interface CellStyle {
  font?: {
    name?: string
    size?: number
    bold?: boolean
    italic?: boolean
    color?: { argb: string }
  }
  fill?: {
    type?: string
    fgColor?: { argb: string }
  }
  alignment?: {
    horizontal?: 'left' | 'center' | 'right' | 'fill' | 'justify' | 'centerContinuous' | 'distributed'
    vertical?: 'top' | 'middle' | 'bottom' | 'distributed' | 'justify'
    wrapText?: boolean
  }
  border?: {
    top?: { style: string; color?: { argb: string } }
    left?: { style: string; color?: { argb: string } }
    bottom?: { style: string; color?: { argb: string } }
    right?: { style: string; color?: { argb: string } }
  }
  numFmt?: string
}

/** 合并单元格区域 */
export interface MergeRegion {
  startRow: number
  startCol: number
  endRow: number
  endCol: number
}

/** 渲染用单元格数据 */
export interface RenderCell {
  row: number
  col: number
  value: string | number | null
  formula?: string
  style: CellStyle
  merge?: MergeRegion
  isMerged?: boolean
  rowSpan?: number
  colSpan?: number
}

/** 工作表渲染数据 */
export interface SheetRenderData {
  name: string
  cells: RenderCell[][]
  rowCount: number
  colCount: number
  merges: MergeRegion[]
  /** 行高映射（行号 -> 像素高度） */
  rowHeights?: Record<number, number>
  /** 列宽映射（列号 -> 像素宽度） */
  colWidths?: Record<number, number>
}

/** 单元格绑定类型 */
export type BindingDataType = 'static' | 'dynamic'

/** 单元格绑定关系 */
export interface CellBinding {
  id: string
  sheetName: string
  cellAddress: string
  fieldKey: string
  dataType: BindingDataType
  /** 动态行的示例行号（1-indexed） */
  templateRow?: number
  /** 动态行引用的解析区域 fieldKey（如 "l6_details"） */
  regionFieldKey?: string
  /** 动态行导出时的列映射：字段名 → 列字母（从解析区域继承，可调整） */
  fieldMapping?: Record<string, string>
  /** 描述模板（仅 config_summary 时生效），如 "{kp_list}" */
  descriptionTemplate?: string
  /** 描述分隔符（仅 config_summary 时生效），默认 "," */
  descriptionSeparator?: string
}

/** 业务字段定义 */
export interface BusinessField {
  key: string
  label: string
  category: 'opportunity' | 'item' | 'l6' | 'kp' | 'system' | 'parse_region'
  description?: string
  /** 来源：系统预定义 or 解析模板定义的动态区域 */
  source?: 'system' | 'parse'
}

/** 产品明细行数据 */
export interface ProductRow {
  [key: string]: string | number | null
}

/** 模板数据 */
export interface TemplateData {
  /** 模板文件二进制 */
  fileBuffer: ArrayBuffer
  /** 模板文件名 */
  fileName: string
  /** 工作表渲染数据 */
  sheets: SheetRenderData[]
  /** 单元格绑定关系 */
  bindings: CellBinding[]
  /** 产品明细数据 */
  productData: ProductRow[]
  /** 静态字段数据 */
  staticData: Record<string, string | number | null>
}

/** 模板编辑器状态 */
export interface TemplateEditorState {
  /** 当前选中的工作表索引 */
  currentSheetIndex: number
  /** 当前选中的单元格 */
  selectedCell: RenderCell | null
  /** 是否正在加载 */
  loading: boolean
}

/** 模板单页（封面/配置页）的持久化结构 */
export interface TemplatePartData {
  fileName?: string
  /** Excel 文件 base64（仅编辑器加载时需要，列表接口会剥离） */
  fileBuffer?: string
  bindings?: CellBinding[]
  /** 配置页 sheet 名模板，支持 {cfg_name} {chassis_form} {cpu_model} */
  sheetNameTemplate?: string
}

/** 导出模板 */
export interface ExportTemplate {
  id: number
  name: string
  display_name: string
  is_default: boolean
  template_json: {
    cover?: TemplatePartData
    config_sheet?: TemplatePartData
  }
  created_at: string
  updated_at: string
}
