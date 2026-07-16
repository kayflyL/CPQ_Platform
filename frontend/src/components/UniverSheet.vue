<template>
  <div 
    ref="univerContainerRef" 
    class="univer-sheet-wrapper"
  >
    <div :id="uniqueContainerId" ref="univerInnerRef" class="univer-container"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { LocaleType, Tools, Univer, UniverInstanceType } from '@univerjs/core'
import { FUniver } from '@univerjs/core/facade'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import '@univerjs/preset-sheets-core/lib/index.css'
import zhCN from '@univerjs/preset-sheets-core/locales/zh-CN'

// 补充 Univer 语言包中缺失的 key，避免显示原始 key 名
if (zhCN['sheets-ui']?.info) {
  zhCN['sheets-ui'].info.error = zhCN['sheets-ui'].info.error || '出现了一个问题'
  zhCN['sheets-ui'].info.forceStringInfo = zhCN['sheets-ui'].info.forceStringInfo || '已强制将内容转换为文本'
}

/**
 * Cell address: "A1", "B2", etc.
 */
interface CellInfo {
  row: number // 0-indexed
  col: number // 0-indexed
  sheetName: string
  sheetId: string
}

const props = withDefaults(defineProps<{
  workbookData: Record<string, any> // Univer workbook snapshot format
  editable?: boolean // 是否启用行高列宽拖拽调整
}>(), {
  editable: false
})

const emit = defineEmits<{
  (e: 'cell-click', cell: CellInfo): void
  (e: 'cell-dblclick', cell: CellInfo, event: MouseEvent): void
  (e: 'row-resize', rowIdx: number, height: number): void
  (e: 'col-resize', colIdx: number, width: number): void
  (e: 'edit'): void
}>()

const univerContainerRef = ref<HTMLElement | null>(null)
const univerInnerRef = ref<HTMLElement | null>(null)
const uniqueContainerId = `univer-container-${Math.random().toString(36).slice(2, 9)}`
let univer: Univer | null = null
let _isRendering = false
let _suppressEdit = false

/**
 * 获取 FUniver API 实例（兼容新旧版本）
 */
function getFUniverAPI(): any {
  if (!univer) return null
  // 优先使用新 API
  if ((univer as any).api?.getFUniver) {
    return (univer as any).api.getFUniver()
  }
  // 回退到旧 API
  return FUniver.newAPI(univer)
}

/**
 * Convert cellAddress (e.g. "A1") to 0-indexed row/col
 */
function cellAddressToRowCol(addr: string): { row: number; col: number } | null {
  const match = addr.match(/^([A-Z]+)(\d+)$/)
  if (!match) return null
  const colStr = match[1]
  const row = parseInt(match[2]) - 1
  let col = 0
  for (let i = 0; i < colStr.length; i++) {
    col = col * 26 + (colStr.charCodeAt(i) - 64)
  }
  col -= 1
  return { row, col }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

async function renderUniver() {
  console.log('[UniverSheet] renderUniver called', {
    hasContainer: !!univerContainerRef.value,
    hasWorkbookData: !!props.workbookData,
    sheetCount: Object.keys(props.workbookData?.sheets || {}).length
  })
  
  if (!univerContainerRef.value || !props.workbookData) {
    console.warn('[UniverSheet] Skipping render - missing container or workbook data')
    return
  }
  
  _isRendering = true
  _suppressEdit = true
  
  // Cleanup old instance
  if (univer) {
    univer.dispose()
    univer = null
  }
  
  console.log('[UniverSheet] Initializing Univer with preset...')
  
  // 正确加载中文语言包
  univer = new Univer({
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: zhCN
    }
  })
  
  const presetConfig = UniverSheetsCorePreset({
    container: uniqueContainerId,
    header: props.editable,
    toolbar: props.editable,
    footer: true,
    formulaBar: props.editable,
    menu: props.editable ? {} : false,
    contextMenu: props.editable
  } as any)
  
  for (const plugin of presetConfig.plugins) {
    if (Array.isArray(plugin)) {
      univer.registerPlugin(plugin[0], plugin[1])
    } else if (plugin) {
      univer.registerPlugin(plugin)
    }
  }
  
  const workbookData = props.workbookData
  univer.createUnit(UniverInstanceType.UNIVER_SHEET, workbookData)
  
  setTimeout(() => {
    if (!univer) return
    const univerAPI = getFUniverAPI()
    
    // Cell click
    if (univerAPI.addEvent && univerAPI.Event?.CellClicked) {
      univerAPI.addEvent(univerAPI.Event.CellClicked, (params: any) => {
        const row = params.row
        const col = params.column
        const workbook = univerAPI.getActiveWorkbook()
        const sheet = workbook?.getActiveSheet()
        const sheetName = sheet?.getSheetName() || ''
        const sheetId = sheet?.getSheetId?.() || ''
        
        if (row !== undefined && col !== undefined) {
          emit('cell-click', { row, col, sheetName, sheetId })
        }
      })
    }
    
    // Edit detection
    if (univerAPI.addEvent && univerAPI.Event?.CommandExecuted) {
      univerAPI.addEvent(univerAPI.Event.CommandExecuted, (_params: any) => {
        if (!_suppressEdit) {
          emit('edit')
        }
      })
    }
    
    _isRendering = false
    _suppressEdit = false
  }, 500)
}

// Watch workbookData changes (template load/switch only)
watch(() => props.workbookData, () => {
  nextTick(() => renderUniver())
})



// Watch previewData
watch(() => props.previewData, () => {
  if (_isRendering) return
  nextTick(() => {
    updatePreviewsInPlace()
  })
}, { deep: true })

onMounted(() => {
  nextTick(() => renderUniver())
})

function getWorkbookData(): Record<string, any> {
  if (!univer) return {}
  const univerAPI = getFUniverAPI()
  const workbook = univerAPI.getActiveWorkbook()
  if (!workbook) return {}
  // 使用 save() 替代已废弃的 getSnapshot()
  return workbook.save() || {}
}

/**
 * Set cell value and background color via Univer API
 * @param row Row index (0-based)
 * @param col Column index (0-based)
 * @param value Cell value
 * @param bgColor Optional background color
 * @param sheetId Optional sheet ID. If not provided, uses active sheet.
 */
function setCellBinding(row: number, col: number, value: string, bgColor?: string, sheetId?: string) {
  if (!univer) return
  const univerAPI = getFUniverAPI()
  const workbook = univerAPI.getActiveWorkbook()
  if (!workbook) return
  
  // 如果指定了 sheetId，必须使用该 sheet，不允许回退到活动 sheet
  let sheet
  if (sheetId) {
    try {
      sheet = workbook.getSheetBySheetId(sheetId)
    } catch (e) {
      console.error('Failed to get sheet by ID:', sheetId, e)
    }
    if (!sheet) {
      console.error('Sheet not found:', sheetId)
      return
    }
  } else {
    // 未指定 sheetId 时，使用活动 sheet
    sheet = workbook.getActiveSheet()
  }
  if (!sheet) return
  
  const range = sheet.getRange(row, col, 1, 1)
  range.setValue(value)
  
  if (bgColor) {
    range.setBackground(bgColor)
  }
}

/**
 * Clear cell binding (remove value and reset background)
 */
function clearCellBinding(row: number, col: number) {
  if (!univer) return
  const univerAPI = getFUniverAPI()
  const workbook = univerAPI.getActiveWorkbook()
  if (!workbook) return
  const sheet = workbook.getActiveSheet()
  if (!sheet) return
  
  const range = sheet.getRange(row, col, 1, 1)
  range.setValue('')
  range.setBackground('#FFFFFF')
}

defineExpose({ getWorkbookData, setCellBinding, clearCellBinding })

onBeforeUnmount(() => {
  if (univer) {
    univer.dispose()
    univer = null
  }
})
</script>

<style scoped>
.univer-sheet-wrapper {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
}

.univer-container {
  width: 100%;
  height: 100%;
}
</style>

<!-- 全局样式：修复右键菜单子菜单文字颜色问题 -->
<style>
/* 确保 Univer 容器撑满 */
.univer-container {
  width: 100% !important;
  height: 100% !important;
  position: relative;
}

.univer-container > div {
  width: 100% !important;
  height: 100% !important;
}

/* Univer 内部 canvas 容器 */
.univer-sheet-wrapper canvas {
  width: 100% !important;
  height: 100% !important;
}

/* 右键菜单所有层级文字颜色 */
[data-u-context-menu-submenu] button,
[data-u-context-menu-submenu] div {
  color: #1f2937 !important; /* gray-800 */
}

/* 右键菜单子菜单容器 */
[data-u-context-menu-submenu] {
  background-color: white !important;
  color: #1f2937 !important;
}

/* 右键菜单项 hover 状态 */
[data-u-context-menu-submenu] button:hover {
  background-color: #f9fafb !important; /* gray-50 */
  color: #1f2937 !important;
}
</style>
