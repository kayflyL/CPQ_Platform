<template>
  <div class="excel-table-container">
    <!-- Sheet Tabs -->
    <div class="sheet-tabs" v-if="sheets.length > 1">
      <a-tabs
        v-model:activeKey="activeSheetIndex"
        type="card"
        size="small"
        @change="onSheetChange"
      >
        <a-tab-pane v-for="(sheet, idx) in sheets" :key="idx" :tab="sheet.name" />
      </a-tabs>
    </div>

    <!-- Preview Container -->
    <div class="a4-preview-container" ref="previewContainerRef">
      <!-- Table Preview -->
      <div 
        class="table-wrapper" 
        ref="tableWrapperRef"
      >
        <table class="excel-table" v-if="currentSheet" :style="getTableStyle()">
          <colgroup>
            <col 
              v-for="colIdx in currentSheet.colCount" 
              :key="colIdx" 
              :style="{ width: getColWidth(colIdx - 1) + 'px' }"
            />
          </colgroup>
          <tbody>
            <tr 
              v-for="(row, rIdx) in currentSheet.cells" 
              :key="rIdx"
              :style="{ height: getRowHeight(rIdx) + 'px' }"
            >
              <template v-for="(cell, cIdx) in row" :key="`${rIdx}-${cIdx}`">
                <td
                  v-if="!cell.isMerged"
                  :rowspan="cell.rowSpan"
                  :colspan="cell.colSpan"
                  :class="[
                    'excel-cell',
                    { 'cell-selected': isSelected(cell) },
                    { 'cell-bound': hasBinding(cell) },
                    { 'cell-editing': isEditing(cell) }
                  ]"
                  :style="getCellStyle(cell)"
                  @click="onCellClick(cell)"
                  @dblclick="onCellDblClick(cell, $event)"
                >
                  <div class="cell-content">
                    <template v-if="isEditing(cell)">
                      <textarea
                        ref="editTextareaRef"
                        v-model="editValue"
                        class="cell-editor"
                        @blur="finishEdit(cell)"
                        @keydown.enter.exact.prevent="finishEdit(cell)"
                        @keydown.escape="cancelEdit"
                      />
                    </template>
                    <template v-else>
                      <span class="cell-value">{{ formatCellValue(cell) }}</span>
                      <span v-if="hasBinding(cell)" class="binding-indicator">🔗</span>
                    </template>
                  </div>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { RenderCell, SheetRenderData, CellStyle } from '@/types/template'
import { useTemplateStore } from '@/store/template'
import { useSettingsStore } from '@/store/settings'

const props = withDefaults(defineProps<{
  sheets: SheetRenderData[]
  overlayMap?: Record<string, string> // key: "sheetName!cellAddress" (e.g. "Sheet1!A1"), value: color
  previewData?: Record<string, string | number> // key: "sheetName!cellAddress", value: preview value
  a4Preview?: boolean // A4 纸张预览模式（固定尺寸 + 缩放），默认 true
}>(), {
  a4Preview: true
})

const emit = defineEmits<{
  (e: 'cell-click', cell: RenderCell): void
  (e: 'cell-edit', cell: RenderCell, newValue: string | number | null): void
}>()

const store = useTemplateStore()
const settingsStore = useSettingsStore()
const activeSheetIndex = ref(0)
const previewContainerRef = ref<HTMLElement | null>(null)
const tableWrapperRef = ref<HTMLElement | null>(null)
const editTextareaRef = ref<HTMLTextAreaElement[] | null>(null)

const currentSheet = computed(() => props.sheets[activeSheetIndex.value] || null)

// 编辑状态
const editingCell = ref<RenderCell | null>(null)
const editValue = ref<string>('')

// A4 尺寸常量（96 DPI）
const A4_WIDTH = 794 // 210mm
const A4_HEIGHT = 1123 // 297mm

// 计算缩放比例
const scaleFactor = computed(() => {
  if (!currentSheet.value) return 1
  
  // 计算表格实际宽度
  let totalWidth = 0
  for (let c = 0; c < currentSheet.value.colCount; c++) {
    totalWidth += getColWidth(c)
  }
  
  // 如果表格宽度超过 A4 宽度，则缩放
  if (totalWidth > A4_WIDTH) {
    return A4_WIDTH / totalWidth
  }
  return 1
})

function onSheetChange(idx: number | string) {
  const index = typeof idx === 'number' ? idx : parseInt(idx as string)
  activeSheetIndex.value = index
  store.switchSheet(index)
}

function isSelected(cell: RenderCell): boolean {
  const sel = store.editorState.selectedCell
  if (!sel) return false
  return sel.row === cell.row && sel.col === cell.col
}

function isEditing(cell: RenderCell): boolean {
  return editingCell.value?.row === cell.row && editingCell.value?.col === cell.col
}

function hasBinding(cell: RenderCell): boolean {
  if (!currentSheet.value) return false
  const addr = `${colToLetter(cell.col)}${cell.row}`
  return !!store.getBindingForCell(currentSheet.value.name, addr)
}

function onCellClick(cell: RenderCell) {
  if (!isEditing(cell)) {
    store.selectCell(cell)
    emit('cell-click', cell)
  }
}

function onCellDblClick(cell: RenderCell, event: MouseEvent) {
  event.stopPropagation()
  editingCell.value = cell
  editValue.value = cell.value?.toString() || ''
  
  nextTick(() => {
    const textarea = editTextareaRef.value?.[0]
    if (textarea) {
      textarea.focus()
      textarea.select()
    }
  })
}

function finishEdit(cell: RenderCell) {
  if (editingCell.value) {
    const newValue = editValue.value
    cell.value = newValue
    emit('cell-edit', cell, newValue)
    editingCell.value = null
  }
}

function cancelEdit() {
  editingCell.value = null
}

function getTableStyle(): Record<string, string> {
  return {
    'table-layout': 'fixed'
  }
}

function getRowHeight(rowIdx: number): number {
  if (!currentSheet.value) return 20
  const baseHeight = currentSheet.value.rowHeights?.[rowIdx + 1] || 20
  
  // 检查该行是否有 wrapText 单元格，计算所需高度
  const row = currentSheet.value.cells[rowIdx]
  if (!row) return baseHeight
  
  let maxLines = 1
  for (const cell of row) {
    if (!cell.style?.alignment?.wrapText) continue
    
    // 获取显示值
    let displayValue = ''
    if (props.previewData && currentSheet.value) {
      const addr = `${currentSheet.value.name}!${colToLetter(cell.col)}${cell.row}`
      const pv = props.previewData[addr]
      if (pv !== undefined && pv !== null) displayValue = String(pv)
    } else if (cell.value !== null && cell.value !== undefined) {
      displayValue = String(cell.value)
    }
    if (!displayValue) continue
    
    // 估算字符宽度（中文字符按 2 个字符宽度计算）
    let charWidth = 0
    for (const ch of displayValue) {
      charWidth += ch.charCodeAt(0) > 127 ? 2 : 1
    }
    
    const colWidthPx = getColWidth(cell.col)
    // 估算每行可容纳的字符数（基于字体大小）
    const fontSize = cell.style?.font?.size || 12
    const pxPerChar = fontSize * 1.333 * 0.6 // 粗略估算
    const charsPerLine = Math.max(1, Math.floor(colWidthPx / pxPerChar))
    const lines = Math.ceil(charWidth / charsPerLine)
    maxLines = Math.max(maxLines, lines)
  }
  
  // 行高 = 基础行高 × 行数（至少保持原始行高）
  const lineHeight = baseHeight
  const neededHeight = lineHeight * maxLines
  return Math.max(baseHeight, neededHeight)
}

function getColWidth(colIdx: number): number {
  if (!currentSheet.value?.colWidths) return 100
  return currentSheet.value.colWidths[colIdx + 1] || 100
}

function getCellStyle(cell: RenderCell): Record<string, string> {
  const style: Record<string, string> = {}
  const s = cell.style

  if (s.font) {
    if (s.font.name) style['font-family'] = s.font.name
    // Excel 字号单位是 pt，1pt ≈ 1.333px
    if (s.font.size) style['font-size'] = `${Math.round(s.font.size * 1.333)}px`
    if (s.font.bold) style['font-weight'] = 'bold'
    if (s.font.italic) style['font-style'] = 'italic'
    if (s.font.color?.argb) style['color'] = argbToRgba(s.font.color.argb)
  }

  if (s.fill?.fgColor?.argb) {
    style['background-color'] = argbToRgba(s.fill.fgColor.argb)
  }

  if (s.alignment) {
    if (s.alignment.horizontal) style['text-align'] = s.alignment.horizontal
    if (s.alignment.vertical) {
      const vMap: Record<string, string> = { top: 'top', middle: 'middle', bottom: 'bottom' }
      style['vertical-align'] = vMap[s.alignment.vertical] || 'middle'
    }
    // 自动换行
    if (s.alignment.wrapText) {
      style['white-space'] = 'normal'
      style['word-wrap'] = 'break-word'
      style['overflow-wrap'] = 'break-word'
    }
  }

  if (s.border) {
    const sides = ['top', 'left', 'bottom', 'right'] as const
    for (const side of sides) {
      const b = s.border[side]
      if (b) {
        const color = b.color?.argb ? argbToRgba(b.color.argb) : 'var(--cpq-text-secondary)'
        const width = b.style === 'thin' ? '1px' : b.style === 'medium' ? '2px' : '1px'
        style[`border-${side}`] = `${width} solid ${color}`
      }
    }
  }

  style['padding'] = '2px 4px'

  // 应用热力图覆盖色
  if (props.overlayMap && currentSheet.value) {
    const addr = `${colToLetter(cell.col)}${cell.row}`
    const key = `${currentSheet.value.name}!${addr}`
    const overlayColor = props.overlayMap[key]
    if (overlayColor) {
      style['background-color'] = overlayColor
    }
  }

  return style
}

function formatCellValue(cell: RenderCell): string {
  // 如果有预览数据，优先显示预览值
  if (props.previewData && currentSheet.value) {
    const addr = `${currentSheet.value.name}!${colToLetter(cell.col)}${cell.row}`
    const previewValue = props.previewData[addr]
    if (previewValue !== undefined && previewValue !== null && previewValue !== '') {
      // 数字格式化：使用全局精度配置
      if (typeof previewValue === 'number') {
        return previewValue.toFixed(settingsStore.numberPrecision)
      }
      return String(previewValue)
    }
  }
  if (cell.value === null || cell.value === undefined) return ''
  // 数字格式化：使用全局精度配置
  if (typeof cell.value === 'number') {
    return cell.value.toFixed(settingsStore.numberPrecision)
  }
  return String(cell.value)
}

function colToLetter(col: number): string {
  let result = ''
  while (col > 0) {
    const mod = (col - 1) % 26
    result = String.fromCharCode(65 + mod) + result
    col = Math.floor((col - 1) / 26)
  }
  return result
}

function argbToRgba(argb: string): string {
  if (!argb || argb.length < 6) return 'var(--cpq-bg-primary)000'
  const clean = argb.replace(/^FF/i, '')
  if (clean.length === 6) return `#${clean}`
  return `#${argb.slice(-6)}`
}
</script>

<style scoped>
.excel-table-container {
  min-width: fit-content;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.sheet-tabs {
  border-bottom: 1px solid var(--cpq-border-dark);
  margin-bottom: 8px;
  width: 100%;
}

/* 预览容器 */
.a4-preview-container {
  width: 100%;
  overflow: auto;
  border: 2px solid var(--cpq-border-primary, var(--cpq-border-dark));
  border-radius: 4px;
  background: var(--cpq-text-primary)fff;
  box-shadow: 0 2px 8px var(--cpq-overlay-b15);
  max-height: 80vh;
}

/* 表格包装器 */
.table-wrapper {
  display: inline-block;
}

.excel-table {
  border-collapse: collapse;
  table-layout: fixed;
}

.excel-cell {
  border: 1px solid var(--cpq-border-light);
  padding: 2px 4px;
  font-size: 12px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: background-color 0.15s;
  background-color: var(--cpq-text-primary)fff;
  color: var(--cpq-text-inverse);
}

.excel-cell:hover {
  outline: 2px solid var(--cpq-color-info);
  outline-offset: -2px;
  z-index: 1;
}

.cell-selected {
  outline: 2px solid var(--cpq-color-success) !important;
  outline-offset: -2px;
  z-index: 2;
  background-color: var(--cpq-bg-selected) !important;
}

.cell-bound {
  box-shadow: inset 0 0 0 1px var(--cpq-color-warning);
}

.cell-editing {
  padding: 0 !important;
  overflow: visible !important;
}

.cell-editor {
  width: 100%;
  height: 100%;
  border: none;
  outline: none;
  padding: 2px 4px;
  font-size: inherit;
  font-family: inherit;
  resize: none;
  background: var(--cpq-bg-highlight);
}

.binding-indicator {
  position: absolute;
  top: 0;
  right: 2px;
  font-size: 10px;
  opacity: 0.7;
}

.cell-value {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
