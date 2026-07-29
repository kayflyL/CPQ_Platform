<template>
  <!-- 热力图预览：纯展示组件，设置页与商机预览弹窗共用。
       由父组件用 a-card 包裹并提供 :loading；本组件只负责把 previewData
       渲染成带区域着色 + 来源 tooltip 的网格。 -->
  <template v-if="previewData">
    <div class="heatmap-container">
      <table class="heatmap-table">
        <tbody>
          <tr v-for="(row, rIdx) in previewData.grid" :key="rIdx">
            <td
              v-for="(cell, cIdx) in row"
              :key="cIdx"
              :class="getCellClass(Number(rIdx), Number(cIdx))"
              :title="getCellTooltip(Number(rIdx), Number(cIdx))"
            >
              {{ cell }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 图例 -->
    <div class="legend">
      <a-space>
        <span class="legend-item"><span class="legend-color header-region"></span>Header</span>
        <span class="legend-item"><span class="legend-color l6-region"></span>L6</span>
        <span class="legend-item"><span class="legend-color kp-region"></span>KP</span>
        <span class="legend-item"><span class="legend-color warranty-region"></span>Warranty</span>
        <span class="legend-item"><span class="legend-color keyword"></span>关键词</span>
        <span class="legend-item"><span class="legend-color extracted"></span>提取值</span>
      </a-space>
    </div>
  </template>
  <template v-else>
    <a-empty description="上传 Excel 文件查看预览" />
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ previewData: any }>()

// 动态颜色映射：内置 4 个区域色 + 备用色板兜底新增区域
const regionColorMap = computed(() => {
  const map: Record<string, string> = {
    'header': 'cell-header',
    'l6': 'cell-l6',
    'kp': 'cell-kp',
    'warranty': 'cell-warranty'
  }

  const palette = [
    'cell-region-1', 'cell-region-2', 'cell-region-3',
    'cell-region-4', 'cell-region-5', 'cell-region-6'
  ]
  let paletteIdx = 0

  if (props.previewData?.region_bounds) {
    for (const regionName of Object.keys(props.previewData.region_bounds)) {
      const key = regionName.toLowerCase()
      if (!(key in map)) {
        map[key] = palette[paletteIdx % palette.length]
        paletteIdx++
      }
    }
  }

  return map
})

function getCellClass(row: number, col: number): string {
  if (!props.previewData?.cell_marks) return ''

  const mark = props.previewData.cell_marks.find(
    (m: any) => Number(m.row) === row && Number(m.col) === col
  )

  if (!mark) return ''

  if (mark.type === 'keyword') return 'cell-keyword'
  if (mark.type === 'extracted') return 'cell-extracted'

  // 动态区域颜色：从 type 提取区域名（如 "l6_region" -> "l6"）
  const regionKey = mark.type.replace('_region', '').toLowerCase()
  return regionColorMap.value[regionKey] || ''
}

function getCellTooltip(row: number, col: number): string {
  if (!props.previewData?.cell_marks) return ''

  const mark = props.previewData.cell_marks.find(
    (m: any) => Number(m.row) === row && Number(m.col) === col
  )

  if (!mark) return ''

  return `${mark.target}: ${mark.value}`
}
</script>

<style scoped>
.heatmap-container {
  overflow: auto;
  max-height: 500px;
  border: 1px solid var(--cpq-border);
  border-radius: 4px;
  background-color: #fff;
}

.heatmap-table {
  border-collapse: collapse;
  font-size: 12px;
  width: 100%;
}

.heatmap-table td {
  border: 1px solid #ddd;
  padding: 4px 8px;
  min-width: 80px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #333;
}

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

.legend {
  margin-top: 12px;
  padding: 8px;
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
  width: 16px;
  height: 16px;
  border-radius: 2px;
}

.legend-color.keyword {
  background-color: #fff3cd;
}

.legend-color.extracted {
  background-color: #d4edda;
}

.legend-color.header-region {
  background-color: #e7f3ff;
}

.legend-color.l6-region {
  background-color: #fff4e6;
}

.legend-color.kp-region {
  background-color: #f3e5f5;
}

.legend-color.warranty-region {
  background-color: #e8f5e9;
}
</style>
