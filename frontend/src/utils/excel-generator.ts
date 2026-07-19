/**
 * ExcelJS 封装工具类
 * 负责：模板解析、样式提取（供模板编辑器预览使用）
 */
import ExcelJS from 'exceljs'
import type {
  SheetRenderData,
  RenderCell,
  CellStyle,
  MergeRegion
} from '@/types/template'

/**
 * 解析 Excel 模板，提取所有工作表的单元格数据和样式
 */
export async function parseExcelTemplate(buffer: ArrayBuffer): Promise<SheetRenderData[]> {
  const workbook = new ExcelJS.Workbook()
  await workbook.xlsx.load(buffer)

  const sheets: SheetRenderData[] = []

  workbook.eachSheet((worksheet) => {
    const merges: MergeRegion[] = []
    const mergeModel = (worksheet as any).model?.merges as string[] | undefined
    
    if (mergeModel) {
      for (const range of mergeModel) {
        const parsed = parseMergeRange(range)
        if (parsed) merges.push(parsed)
      }
    }

    const rowCount = worksheet.rowCount
    const colCount = worksheet.columnCount
    const cells: RenderCell[][] = []

    // 构建合并区域映射（用于标记被合并的单元格）
    const mergeMap = new Map<string, MergeRegion>()
    for (const m of merges) {
      for (let r = m.startRow; r <= m.endRow; r++) {
        for (let c = m.startCol; c <= m.endCol; c++) {
          mergeMap.set(`${r}_${c}`, m)
        }
      }
    }

    // 计算实际有数据的最大行数（过滤尾部空行）
    // 判断标准：有文字/数字，或者有边框/背景色，都算有效行
    let actualRowCount = 0
    for (let r = rowCount; r >= 1; r--) {
      let hasData = false
      for (let c = 1; c <= colCount; c++) {
        const cell = worksheet.getCell(r, c)
        // 检查是否有值
        if (cell.value !== null && cell.value !== undefined && cell.value !== '') {
          hasData = true
          break
        }
        // 检查是否有边框
        const border = cell.border
        if (border && (border.top || border.left || border.bottom || border.right)) {
          hasData = true
          break
        }
        // 检查是否有背景填充
        const fill = cell.fill
        if (fill && (fill as any).fgColor && (fill as any).fgColor.argb && (fill as any).fgColor.argb !== 'FF000000') {
          hasData = true
          break
        }
      }
      if (hasData) {
        actualRowCount = r
        break
      }
    }
    // 如果全是空行，至少保留1行
    if (actualRowCount === 0) actualRowCount = Math.min(rowCount, 1)

    for (let r = 1; r <= actualRowCount; r++) {
      const row: RenderCell[] = []
      for (let c = 1; c <= colCount; c++) {
        const cell = worksheet.getCell(r, c)
        const merge = mergeMap.get(`${r}_${c}`)
        const isTopLeft = merge && r === merge.startRow && c === merge.startCol
        
        const renderCell: RenderCell = {
          row: r,
          col: c,
          value: extractCellValue(cell),
          style: extractCellStyle(cell),
          isMerged: !!merge && !isTopLeft
        }

        if (cell.type === ExcelJS.ValueType.Formula) {
          renderCell.formula = (cell as any).formula
        }

        if (isTopLeft && merge) {
          renderCell.merge = merge
          renderCell.rowSpan = merge.endRow - merge.startRow + 1
          renderCell.colSpan = merge.endCol - merge.startCol + 1
        }

        row.push(renderCell)
      }
      cells.push(row)
    }

    // 提取行高和列宽
    const rowHeights: Record<number, number> = {}
    const colWidths: Record<number, number> = {}
    
    for (let r = 1; r <= rowCount; r++) {
      const row = worksheet.getRow(r)
      if (row.height) {
        // Excel 行高单位是 points，1 point ≈ 1.333 pixels
        rowHeights[r] = Math.round(row.height * 1.333)
      }
    }
    
    for (let c = 1; c <= colCount; c++) {
      const col = worksheet.getColumn(c)
      if (col.width) {
        // Excel 列宽单位是字符宽度，1 字符 ≈ 7 pixels
        colWidths[c] = Math.round(col.width * 7)
      }
    }

    sheets.push({
      name: worksheet.name,
      cells,
      rowCount: actualRowCount,  // 使用过滤后的实际行数
      colCount,
      merges,
      rowHeights,
      colWidths
    })
  })

  return sheets
}

/**
 * 解析合并区域字符串，如 "A1:E1" -> MergeRegion
 */
function parseMergeRange(range: string): MergeRegion | null {
  const match = range.match(/^([A-Z]+)(\d+):([A-Z]+)(\d+)$/)
  if (!match) return null
  return {
    startRow: parseInt(match[2]),
    startCol: colToNum(match[1]),
    endRow: parseInt(match[4]),
    endCol: colToNum(match[3])
  }
}

/**
 * 列字母转数字
 */
function colToNum(col: string): number {
  let num = 0
  for (let i = 0; i < col.length; i++) {
    num = num * 26 + (col.charCodeAt(i) - 64)
  }
  return num
}

/**
 * 提取单元格值
 */
function extractCellValue(cell: ExcelJS.Cell): string | number | null {
  if (cell.type === ExcelJS.ValueType.Formula) {
    const result = (cell.value as any).result
    if (typeof result === 'number') return result
    if (typeof result === 'string') return result
    return null
  }
  if (cell.value === null || cell.value === undefined) return null
  if (typeof cell.value === 'object') {
    // 富文本类型：{richText: [{text, font}, ...]}
    if ('richText' in cell.value && Array.isArray(cell.value.richText)) {
      return cell.value.richText.map((item: any) => item.text || '').join('')
    }
    if ('text' in cell.value) return String(cell.value.text)
    if ('result' in cell.value) return cell.value.result as string | number
    return JSON.stringify(cell.value)
  }
  return cell.value as string | number
}

/**
 * 提取单元格样式
 */
function extractCellStyle(cell: ExcelJS.Cell): CellStyle {
  const style: CellStyle = {}
  const s = cell.style

  if (s.font && Object.keys(s.font).length > 0) {
    style.font = {
      name: s.font.name,
      size: s.font.size,
      bold: s.font.bold,
      italic: s.font.italic,
      color: s.font.color ? { argb: (s.font.color as any).argb || '#000000' } : undefined
    }
  }

  if (s.fill && s.fill.type) {
    style.fill = {
      type: s.fill.type,
      fgColor: (s.fill as any).fgColor ? { argb: (s.fill as any).fgColor.argb } : undefined
    }
  }

  if (s.alignment && Object.keys(s.alignment).length > 0) {
    style.alignment = {
      horizontal: s.alignment.horizontal as any,
      vertical: s.alignment.vertical as any,
      wrapText: s.alignment.wrapText
    }
  }

  if (s.border && Object.keys(s.border).length > 0) {
    style.border = {}
    for (const side of ['top', 'left', 'bottom', 'right'] as const) {
      if ((s.border as any)[side]) {
        (style.border as any)[side] = {
          style: (s.border as any)[side].style,
          color: (s.border as any)[side].color
            ? { argb: (s.border as any)[side].color.argb }
            : undefined
        }
      }
    }
  }

  if (s.numFmt) {
    style.numFmt = s.numFmt
  }

  return style
}

/**
 * 将样式应用到 exceljs 单元格
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function applyCellStyle(cell: ExcelJS.Cell, style: CellStyle) {
  if (style.font) {
    cell.font = {
      name: style.font.name,
      size: style.font.size,
      bold: style.font.bold,
      italic: style.font.italic,
      color: style.font.color ? { argb: style.font.color.argb } : undefined
    }
  }
  if (style.fill) {
    cell.fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: style.fill.fgColor ? { argb: style.fill.fgColor.argb } : undefined
    } as any
  }
  if (style.alignment) {
    cell.alignment = {
      horizontal: style.alignment.horizontal,
      vertical: style.alignment.vertical,
      wrapText: style.alignment.wrapText
    }
  }
  if (style.border) {
    cell.border = style.border as any
  }
  if (style.numFmt) {
    cell.numFmt = style.numFmt
  }
}

