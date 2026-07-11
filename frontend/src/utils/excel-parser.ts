/**
 * Excel 解析引擎
 * 混合模型：静态字段用CellBinding精确读取，动态区域用关键词定位
 */
import ExcelJS from 'exceljs'
import type { ParseTemplate, DynamicRegion, ParsedResult, ParsedRow } from '@/types/parseTemplate'
import type { CellBinding } from '@/types/template'

/** 列字母转数字 (A=1, B=2, ..., Z=26, AA=27) */
function colToNum(col: string): number {
  let num = 0
  for (let i = 0; i < col.length; i++) {
    num = num * 26 + (col.toUpperCase().charCodeAt(i) - 64)
  }
  return num
}

/** 提取单元格文本值（处理合并单元格、公式等） */
function extractCellValue(cell: ExcelJS.Cell): string | number | null {
  if (!cell || cell.value === null || cell.value === undefined) return null
  
  if (cell.type === ExcelJS.ValueType.Formula) {
    const result = (cell.value as ExcelJS.CellFormulaValue).result
    if (typeof result === 'number') return result
    if (typeof result === 'string') return result
    return null
  }
  
  if (typeof cell.value === 'object') {
    // Rich text: { richText: [{text: '...'}, ...] }
    if ('richText' in cell.value) {
      const richText = (cell.value as ExcelJS.CellRichTextValue).richText
      return richText.map(r => r.text).join('')
    }
    if ('result' in cell.value) return (cell.value as ExcelJS.CellFormulaValue).result as string | number
    return JSON.stringify(cell.value)
  }
  
  return cell.value as string | number
}

/** 检查单元格文本是否匹配关键词列表（逗号分隔） */
function matchesKeywords(cellText: string | null, keywords: string): boolean {
  if (!cellText) return false
  const normalized = cellText.trim().toLowerCase()
  const keywordList = keywords.split(',').map(k => k.trim().toLowerCase()).filter(Boolean)
  return keywordList.some(kw => normalized.includes(kw))
}

/** 查找区域起止行号 */
function findRegionBounds(
  worksheet: ExcelJS.Worksheet,
  startKeywords: string,
  endKeywords: string
): { startRow: number; endRow: number } | null {
  const rowCount = worksheet.rowCount
  let startRow = -1
  let endRow = -1

  for (let r = 1; r <= rowCount; r++) {
    const row = worksheet.getRow(r)
    let rowText = ''
    row.eachCell({ includeEmpty: true }, (cell) => {
      const val = extractCellValue(cell)
      if (val !== null) rowText += ' ' + String(val)
    })

    if (startRow === -1 && matchesKeywords(rowText, startKeywords)) {
      startRow = r
    } else if (startRow !== -1 && endRow === -1 && matchesKeywords(rowText, endKeywords)) {
      endRow = r
      break
    }
  }

  if (startRow === -1) return null
  // 如果没找到结束关键词，取到最后一行
  if (endRow === -1) endRow = rowCount

  return { startRow, endRow }
}

/** 解析单个动态区域 */
function parseDynamicRegion(
  workbook: ExcelJS.Workbook,
  region: DynamicRegion,
  warnings: string[]
): ParsedRow[] {
  const rows: ParsedRow[] = []

  // 遍历所有工作表查找区域
  const searchResult = { bounds: null as { startRow: number; endRow: number } | null, sheet: null as ExcelJS.Worksheet | null }

  workbook.eachSheet((worksheet) => {
    if (searchResult.bounds) return
    const found = findRegionBounds(worksheet, region.startKeywords, region.endKeywords)
    if (found) {
      searchResult.bounds = found
      searchResult.sheet = worksheet
    }
  })

  if (!searchResult.bounds || !searchResult.sheet) {
    warnings.push(`区域 "${region.name}"：未找到匹配 "${region.startKeywords}" 的区域`)
    return rows
  }

  // 数据行从起始行+1开始（跳过关键词/表头行）
  const dataStartRow = searchResult.bounds.startRow + 1
  const dataEndRow = searchResult.bounds.endRow - 1

  if (dataStartRow > dataEndRow) {
    warnings.push(`区域 "${region.name}"：区域内无数据行`)
    return rows
  }

  // 按列映射提取数据
  for (let r = dataStartRow; r <= dataEndRow; r++) {
    const row = searchResult.sheet.getRow(r)
    const parsedRow: ParsedRow = {}
    let hasData = false

    for (const [fieldKey, colLetter] of Object.entries(region.fieldMapping)) {
      const colNum = colToNum(colLetter)
      const cell = row.getCell(colNum)
      const value = extractCellValue(cell)
      parsedRow[fieldKey] = value
      if (value !== null && value !== '') hasData = true
    }

    // 跳过完全空行
    if (hasData) {
      rows.push(parsedRow)
    }
  }

  if (rows.length === 0) {
    warnings.push(`区域 "${region.name}"：区域内未提取到有效数据`)
  }

  return rows
}

/** 解析静态字段 */
function parseStaticBindings(
  workbook: ExcelJS.Workbook,
  bindings: CellBinding[],
  warnings: string[]
): Record<string, string | number | null> {
  const data: Record<string, string | number | null> = {}

  for (const binding of bindings) {
    const sheet = workbook.getWorksheet(binding.sheetName)
    if (!sheet) {
      warnings.push(`静态字段 "${binding.fieldKey}"：工作表 "${binding.sheetName}" 不存在`)
      continue
    }
    const cell = sheet.getCell(binding.cellAddress)
    data[binding.fieldKey] = extractCellValue(cell)
  }

  return data
}

/**
 * 主入口：根据解析模板解析Excel文件
 */
export async function parseExcelByTemplate(
  buffer: ArrayBuffer,
  template: ParseTemplate
): Promise<ParsedResult> {
  const workbook = new ExcelJS.Workbook()
  await workbook.xlsx.load(buffer)

  const warnings: string[] = []

  // 1. 解析静态字段
  const staticData = parseStaticBindings(workbook, template.staticBindings, warnings)

  // 2. 解析动态区域
  const dynamicData: Record<string, ParsedRow[]> = {}
  for (const region of template.dynamicRegions) {
    dynamicData[region.name] = parseDynamicRegion(workbook, region, warnings)
  }

  return { staticData, dynamicData, warnings }
}

/**
 * 仅用于预览：解析上传的Excel样本，返回原始数据供热力图等使用
 */
export async function parseExcelRawData(
  buffer: ArrayBuffer
): Promise<{ name: string; rows: (string | number | null)[][] }[]> {
  const workbook = new ExcelJS.Workbook()
  await workbook.xlsx.load(buffer)

  const sheets: { name: string; rows: (string | number | null)[][] }[] = []

  workbook.eachSheet((worksheet) => {
    const rows: (string | number | null)[][] = []
    for (let r = 1; r <= worksheet.rowCount; r++) {
      const row: (string | number | null)[] = []
      const worksheetRow = worksheet.getRow(r)
      for (let c = 1; c <= worksheet.columnCount; c++) {
        const cell = worksheetRow.getCell(c)
        row.push(extractCellValue(cell))
      }
      rows.push(row)
    }
    sheets.push({ name: worksheet.name, rows })
  })

  return sheets
}
