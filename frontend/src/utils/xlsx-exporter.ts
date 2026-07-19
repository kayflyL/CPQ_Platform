/**
 * 纯前端 Univer 工作簿 → xlsx 导出（exceljs 写出侧）
 *
 * 读取侧（UniverSheet.getResolvedWorkbook）用 FRange.getCellStyleData() 拿到
 * 已解析、内联的样式，绕开 Univer 快照里 cell.s 为数字样式 ID 的坑；
 * 本工具只认 ResolvedWorkbook 这个与 Univer 解耦的中间结构。
 */
import ExcelJS from 'exceljs'

// Univer IStyleData 子集（不依赖 @univerjs 类型，保持工具独立）
export type IColor = IColorStyle | string
export interface IColorStyle {
  rgb?: string
  th?: number
}
export interface IBorder {
  s?: number // BorderStyleTypes
  cl?: IColor
}
export interface IStyleData {
  ff?: string // font family
  fs?: number // font size (pt)
  bl?: number // FontWeight 0/1
  it?: number // FontItalic 0/1
  ul?: { s?: number; cl?: IColor }
  st?: { s?: number; cl?: IColor }
  cl?: IColor // font color
  bg?: IColor // background
  bd?: { t?: IBorder; r?: IBorder; b?: IBorder; l?: IBorder }
  ht?: number // HorizontalAlign
  vt?: number // VerticalAlign
  tb?: number // WrapStrategy
  n?: { pattern: string }
}

export interface ResolvedMerge {
  startRow: number
  startColumn: number
  endRow: number
  endColumn: number
}
export interface ResolvedCell {
  row: number
  col: number
  v: any
  style: IStyleData | null
}
export interface ResolvedSheet {
  name: string
  cells: ResolvedCell[]
  merges: ResolvedMerge[]
  rowHeights: Record<number, number> // Univer px
  colWidths: Record<number, number> // Univer px
}
export interface ResolvedWorkbook {
  sheets: ResolvedSheet[]
}

// BorderStyleTypes → exceljs border style
const BORDER_STYLE_MAP: Record<number, string> = {
  1: 'thin',
  2: 'hair',
  3: 'dotted',
  4: 'dashed',
  5: 'dashDot',
  6: 'dashDotDot',
  7: 'double',
  8: 'medium',
  9: 'mediumDashed',
  10: 'mediumDashDot',
  11: 'mediumDashDotDot',
  12: 'slantDashDot',
}
// HorizontalAlign → exceljs horizontal
const H_ALIGN_MAP: Record<number, string> = {
  1: 'left',
  2: 'center',
  3: 'right',
  4: 'justify',
  5: 'justify',
  6: 'distributed',
}
// VerticalAlign → exceljs vertical
const V_ALIGN_MAP: Record<number, string> = {
  1: 'top',
  2: 'middle',
  3: 'bottom',
}

/** Univer rgb（6 或 8 位 hex，可能带 #）→ exceljs argb（8 位） */
function toArgb(rgb?: string): string | undefined {
  if (!rgb) return undefined
  const s = rgb.replace(/^#/, '')
  if (/^[0-9a-fA-F]{8}$/.test(s)) return s
  if (/^[0-9a-fA-F]{6}$/.test(s)) return 'FF' + s
  return undefined
}

/**
 * 从 Univer 颜色值提取 argb。
 * 真实颜色是 {rgb} 对象；裸字符串（如 "000000"）是 openpyxl 导入时给「无填充」单元格
 * 写入的默认伪影 —— 必须跳过，否则会把几乎所有单元格涂成黑底。
 */
function extractColor(c: IColor | undefined | null): string | undefined {
  if (!c || typeof c !== 'object') return undefined
  return toArgb(c.rgb)
}

function applyStyle(cell: ExcelJS.Cell, style: IStyleData | null) {
  if (!style) return

  const font: Record<string, any> = {}
  if (style.ff) font.name = style.ff
  if (typeof style.fs === 'number') font.size = style.fs
  if (style.bl === 1) font.bold = true
  if (style.it === 1) font.italic = true
  if (style.ul && style.ul.s === 1) font.underline = true
  if (style.st && style.st.s === 1) font.strike = true
  const fc = extractColor(style.cl)
  if (fc) font.color = { argb: fc }
  if (Object.keys(font).length) cell.font = font as ExcelJS.Font

  const bc = extractColor(style.bg)
  if (bc) {
    cell.fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: bc },
    } as ExcelJS.FillPattern
  }

  const align: Record<string, any> = {}
  const h = H_ALIGN_MAP[style.ht as number]
  if (h) align.horizontal = h
  const v = V_ALIGN_MAP[style.vt as number]
  if (v) align.vertical = v
  if (style.tb === 3) align.wrapText = true // WrapStrategy.WRAP
  if (Object.keys(align).length) cell.alignment = align as ExcelJS.Alignment

  if (style.bd) {
    const sides: [keyof typeof style.bd, string][] = [
      ['t', 'top'],
      ['r', 'right'],
      ['b', 'bottom'],
      ['l', 'left'],
    ]
    const border: Record<string, any> = {}
    for (const [side, name] of sides) {
      const e = (style.bd as any)[side] as IBorder | undefined
      if (e && typeof e.s === 'number' && e.s !== 0) {
        const argb = extractColor(e.cl)
        border[name] = {
          style: BORDER_STYLE_MAP[e.s] || 'thin',
          color: argb ? { argb } : undefined,
        }
      }
    }
    if (Object.keys(border).length) cell.border = border as Partial<ExcelJS.Borders>
  }

  if (style.n && style.n.pattern) cell.numFmt = style.n.pattern
}

/**
 * 将 ResolvedWorkbook 写成 .xlsx Blob
 */
export async function resolvedWorkbookToXlsx(wb: ResolvedWorkbook): Promise<Blob> {
  const workbook = new ExcelJS.Workbook()

  for (const sh of wb.sheets) {
    const ws = workbook.addWorksheet(sh.name || 'Sheet')

    // 合并：0-indexed → 1-indexed。先合并再写锚点值（非锚点已在读取阶段过滤）
    for (const m of sh.merges) {
      ws.mergeCells(m.startRow + 1, m.startColumn + 1, m.endRow + 1, m.endColumn + 1)
    }

    for (const c of sh.cells) {
      const cell = ws.getCell(c.row + 1, c.col + 1)
      cell.value = c.v ?? null
      applyStyle(cell, c.style)
    }

    // 行高：Univer px → exceljs points（1pt = 4/3 px → pt = px * 0.75）
    for (const [k, h] of Object.entries(sh.rowHeights)) {
      ws.getRow(Number(k) + 1).height = h * 0.75
    }
    // 列宽：Univer px → exceljs 字符宽（≈ px / 8.66，与 excel_to_snapshot 的 *8.66 互逆）
    for (const [k, w] of Object.entries(sh.colWidths)) {
      ws.getColumn(Number(k) + 1).width = w / 8.66
    }
  }

  const buffer = await workbook.xlsx.writeBuffer()
  return new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}
