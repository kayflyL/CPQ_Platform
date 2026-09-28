<template>
  <!-- 交互式解析网格：解析弹窗 v3 专用（设置页仍用纯展示的 ParseHeatmapPreview）。
       行号列点击/拖选 = 行段操作；表头列字母在「点选列」模式下可点 = 绑定字段；
       数据格点击 = 向父组件要「格子档案」（出处 dossier）。 -->
  <template v-if="previewData">
    <div class="igrid-container" @mouseup="dragging = false">
      <table class="igrid-table">
        <thead>
          <tr>
            <th class="gutter-head">#</th>
            <th
              v-for="cIdx in colCount"
              :key="'h' + cIdx"
              class="col-head"
              :class="{ pickable: pickMode }"
              @click="onColHeadClick(cIdx - 1)"
            >
              <span class="col-letter">{{ colLetter(cIdx - 1) }}</span>
              <span
                v-for="f in fieldsOnCol(colLetter(cIdx - 1))"
                :key="f"
                class="col-bind-badge"
                :class="{ picking: pickField === f }"
              >{{ fieldLabels[f] || f }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, rIdx) in previewData.grid"
            :key="rIdx"
            :class="{
              'row-selected': selectedSet.has(Number(rIdx)),
              'row-skipped': skippedSet.has(Number(rIdx)),
              'row-region-end': isRegionEndRow(Number(rIdx))
            }"
          >
            <td
              class="gutter-cell"
              :class="{ 'gutter-selected': selectedSet.has(Number(rIdx)), 'gutter-skipped': skippedSet.has(Number(rIdx)) }"
              @mousedown.prevent="onGutterDown(Number(rIdx))"
              @mouseenter="onGutterEnter(Number(rIdx))"
            >{{ Number(rIdx) + 1 }}</td>
            <td
              v-for="(cell, cIdx) in row"
              :key="cIdx"
              :class="[getCellClass(Number(rIdx), Number(cIdx)), { 'cell-active': isActive(Number(rIdx), Number(cIdx)) }]"
              @click="emit('cell-click', { row: Number(rIdx), col: Number(cIdx) })"
            >{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="pickMode" class="pick-hint">
      <span v-if="pickField">正在为「{{ fieldLabels[pickField] || pickField }}」选列：点击上方列字母完成绑定</span>
      <span v-else>点选列模式</span>
      <a class="pick-cancel" @click="emit('pick-cancel')">退出点列</a>
    </div>

    <div class="legend">
      <a-space wrap>
        <span v-for="item in regionLegend" :key="item.name" class="legend-item">
          <span class="legend-color" :style="{ backgroundColor: item.color }"></span>{{ item.name }}
        </span>
        <span class="legend-item"><span class="legend-color keyword"></span>关键词</span>
        <span class="legend-item"><span class="legend-color extracted"></span>提取值</span>
        <span class="legend-item"><span class="legend-color skipped"></span>已跳过行</span>
      </a-space>
    </div>
  </template>
  <template v-else>
    <a-empty description="暂无预览数据" />
  </template>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{
  previewData: any
  selectedRows: number[]
  skippedRows: number[]
  pickMode: boolean
  pickField?: string | null
  colBinds: Record<string, string>
  fieldLabels: Record<string, string>
  activeCell?: { row: number; col: number } | null
}>()

const emit = defineEmits<{
  (e: 'toggle-row', row: number, op: 'add' | 'remove'): void
  (e: 'cell-click', cell: { row: number; col: number }): void
  (e: 'pick-column', letter: string): void
  (e: 'pick-cancel'): void
}>()

const colCount = computed(() => props.previewData?.grid?.[0]?.length || 0)
const selectedSet = computed(() => new Set(props.selectedRows))
const skippedSet = computed(() => new Set(props.skippedRows))

// 行号列拖选：mousedown 定基调（首行已选→本次为取消，否则为加选），
// mouseenter 沿途套用同一操作，window mouseup 收尾。
const dragging = ref(false)
let dragOp: 'add' | 'remove' = 'add'

function onGutterDown(row: number) {
  dragOp = selectedSet.value.has(row) ? 'remove' : 'add'
  dragging.value = true
  emit('toggle-row', row, dragOp)
}

function onGutterEnter(row: number) {
  if (!dragging.value) return
  if (selectedSet.value.has(row) === (dragOp === 'add')) return
  emit('toggle-row', row, dragOp)
}

function onWindowUp() {
  dragging.value = false
}

onMounted(() => window.addEventListener('mouseup', onWindowUp))
onBeforeUnmount(() => window.removeEventListener('mouseup', onWindowUp))

function onColHeadClick(colIdx: number) {
  if (!props.pickMode) return
  emit('pick-column', colLetter(colIdx))
}

function fieldsOnCol(letter: string): string[] {
  return Object.keys(props.colBinds).filter(f => props.colBinds[f] === letter)
}

function isActive(row: number, col: number): boolean {
  return props.activeCell?.row === row && props.activeCell?.col === col
}

// 收口行（region_ends 生效后下一区域的首行）右侧标边界记号
function isRegionEndRow(row: number): boolean {
  const bounds = props.previewData?.region_bounds || {}
  return Object.values(bounds).some((b: any) => Number(b?.start_row) === row)
}

function colLetter(idx: number): string {
  let s = ''
  let n = idx
  while (n >= 0) {
    s = String.fromCharCode(65 + (n % 26)) + s
    n = Math.floor(n / 26) - 1
  }
  return s
}

// 区域着色：与 ParseHeatmapPreview 同一套规则
const regionColorStyles: Record<string, string> = {
  'cell-header': '#e7f3ff',
  'cell-l6': '#fff4e6',
  'cell-kp': '#f3e5f5',
  'cell-warranty': '#e8f5e9',
  'cell-region-1': '#fce4ec',
  'cell-region-2': '#e0f7fa',
  'cell-region-3': '#fff8e1',
  'cell-region-4': '#ede7f6',
  'cell-region-5': '#e8eaf6',
  'cell-region-6': '#efebe9'
}

const regionColorMap = computed(() => {
  const map: Record<string, string> = {
    header: 'cell-header', l6: 'cell-l6', kp: 'cell-kp', warranty: 'cell-warranty'
  }
  const palette = ['cell-region-1', 'cell-region-2', 'cell-region-3',
                   'cell-region-4', 'cell-region-5', 'cell-region-6']
  let i = 0
  for (const key of Object.keys(props.previewData?.region_bounds || {})) {
    const k = key.toLowerCase()
    if (!(k in map)) map[k] = palette[i++ % palette.length]
  }
  return map
})

const regionLegend = computed(() => {
  const bounds = props.previewData?.region_bounds || {}
  return Object.keys(bounds).map(key => ({
    name: bounds[key]?.region_name || key,
    color: regionColorStyles[regionColorMap.value[key.toLowerCase()]] || '#eeeeee'
  }))
})

function findMark(row: number, col: number): any {
  return (props.previewData?.cell_marks || []).find(
    (m: any) => Number(m.row) === row && Number(m.col) === col)
}

function getCellClass(row: number, col: number): string {
  const mark = findMark(row, col)
  if (!mark) return ''
  if (mark.type === 'keyword') return 'cell-keyword'
  if (mark.type === 'extracted') return 'cell-extracted'
  return regionColorMap.value[String(mark.type).replace('_region', '').toLowerCase()] || ''
}

defineExpose({ colLetter })
</script>

<style scoped>
.igrid-container {
  overflow: auto;
  max-height: 100%;
  border: 1px solid var(--cpq-border);
  border-radius: 6px;
  background-color: #fff;
}

.igrid-table {
  border-collapse: collapse;
  font-size: 12px;
}

.igrid-table th,
.igrid-table td {
  border: 1px solid #ddd;
  padding: 4px 8px;
  white-space: nowrap;
}

.igrid-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #fafafa;
  font-weight: 600;
}

.gutter-head,
.gutter-cell {
  position: sticky;
  left: 0;
  z-index: 1;
  background: #fafafa;
  color: #999;
  text-align: center;
  min-width: 34px;
  user-select: none;
  cursor: pointer;
  font-size: 11px;
}

.igrid-table thead .gutter-head {
  z-index: 3;
}

.gutter-cell:hover {
  background: #e6f4ff;
  color: #1677ff;
}

.gutter-selected {
  background: #1677ff !important;
  color: #fff !important;
}

.gutter-skipped {
  background: #d9d9d9 !important;
  color: #888 !important;
  text-decoration: line-through;
}

.col-head {
  min-width: 80px;
  max-width: 160px;
  text-align: center;
  vertical-align: middle;
}

.col-head.pickable {
  cursor: pointer;
  background: #fffbe6;
  border-color: #faad14;
}

.col-head.pickable:hover {
  background: #fff1b8;
}

.col-letter {
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.col-bind-badge {
  display: inline-block;
  margin-left: 4px;
  padding: 0 4px;
  font-size: 10px;
  line-height: 16px;
  border-radius: 3px;
  background: #e6f4ff;
  color: #1677ff;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

.col-bind-badge.picking {
  background: #faad14;
  color: #fff;
  animation: badge-pulse 1s ease-in-out infinite;
}

@keyframes badge-pulse {
  50% { opacity: 0.55; }
}

.igrid-table td:not(.gutter-cell) {
  min-width: 80px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #333;
  cursor: pointer;
}

.igrid-table td:not(.gutter-cell):hover {
  outline: 1px solid #91caff;
  outline-offset: -1px;
}

.cell-active {
  outline: 2px solid #1677ff !important;
  outline-offset: -2px;
}

.row-selected td {
  background-image: linear-gradient(rgba(22, 119, 255, 0.18), rgba(22, 119, 255, 0.18));
}

.row-skipped td {
  color: #aaa;
  text-decoration: line-through;
  text-decoration-color: #bbb;
}

.row-region-end td:first-child {
  box-shadow: inset 3px 0 0 #722ed1;
}

.cell-keyword {
  background-color: #fff3cd;
  font-weight: 600;
}

.cell-extracted {
  background-color: #d4edda;
  font-weight: 600;
}

.pick-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #d48806;
  display: flex;
  align-items: center;
  gap: 10px;
}

.pick-cancel {
  color: var(--cpq-text-muted, #888);
  cursor: pointer;
}

.pick-cancel:hover {
  color: #1677ff;
}

.legend {
  margin-top: 8px;
  padding: 6px 8px;
  background: var(--cpq-bg-secondary);
  border-radius: 4px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.legend-color {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 2px;
}

.legend-color.keyword { background: #fff3cd; }
.legend-color.extracted { background: #d4edda; }
.legend-color.skipped { background: #d9d9d9; }

/* 着色类：与 ParseHeatmapPreview 同一套（scoped 样式不跨组件，必须本组件自带，
   否则 getCellClass 返回的类名无处落地，L6/KP/关键词/提取值格子全部裸白底） */
.cell-keyword {
  background-color: #fff3cd;
  font-weight: 600;
}

.cell-extracted {
  background-color: #d4edda;
  font-weight: 600;
}

.cell-header {
  background-color: #e7f3ff;
}

.cell-l6 {
  background-color: #fff4e6;
}

.cell-kp {
  background-color: #f3e5f5;
}

.cell-warranty {
  background-color: #e8f5e9;
}

.cell-region-1 { background-color: #fce4ec; }
.cell-region-2 { background-color: #e0f7fa; }
.cell-region-3 { background-color: #fff8e1; }
.cell-region-4 { background-color: #ede7f6; }
.cell-region-5 { background-color: #e8eaf6; }
.cell-region-6 { background-color: #efebe9; }
</style>
