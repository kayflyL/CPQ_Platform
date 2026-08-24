<script setup lang="ts">
/**
 * 服务器俯视图（SVG）—— 策略中心-选型配置页「服务器图」视图。
 * 纯展示 + 交互组件：区域几何/名称/关联字段来自 @/constants/serverAnatomy（数据驱动），
 * 本组件只负责渲染与点击回传，不感知规则内容。
 */
import { computed, ref } from 'vue'
import type { AnatomyRegion, AnatomyView } from '@/constants/serverAnatomy'

interface DecItem {
  type: 'rect' | 'circle'
  x?: number
  y?: number
  w?: number
  h?: number
  cx?: number
  cy?: number
  r?: number
  cls: string
  label?: string
}

const props = withDefaults(defineProps<{
  regions: AnatomyRegion[]
  counts: Record<string, number>
  view?: AnatomyView
  /** 装饰模式：rules=兼容规则（0/命中徽标与未配置虚线）；plain=纯解剖图（无规则残留） */
  decorMode?: 'rules' | 'plain'
  /** 自定义徽标文本（id → 文案），缺省显示 counts 数字 */
  badges?: Record<string, string>
  activeId: string | null
  /** 规则聚焦高亮区域（双向联动：点规则 → 地图高亮命中区域） */
  highlightIds?: string[]
  /** 配置沙盒：硬件数量 → 原有装饰元素按数量截显（无图纸回退图，没有可显隐图层） */
  sandboxCounts?: { gpu?: number; cpu?: number; dimm?: number; drives?: number; psu?: number }
}>(), {
  view: 'top',
  decorMode: 'rules',
  highlightIds: () => [],
})
const emit = defineEmits<{
  select: [id: string | null, region: AnatomyRegion | null]
  hover: [id: string | null, region: AnatomyRegion | null]
  /** HTML5 拖放：规则卡片拖到区域上放下 */
  'drop-rule': [ruleId: string, uid: string]
}>()
const viewLabel = computed(() => props.view === 'top' ? '服务器俯视图' : props.view === 'front' ? '服务器前视图' : '服务器后视图')
const sideLabel = computed(() => props.view === 'top' ? '前置 ◀' : props.view === 'front' ? '前面板' : '后面板')
const sideLabelEnd = computed(() => props.view === 'top' ? '▶ 后置' : '')
/** 拖放悬停区域 id（投放目标高亮） */
const dragUid = ref<string | null>(null)
function onDrop(e: DragEvent, uid: string) {
  const ruleId = e.dataTransfer?.getData('text/plain') ?? ''
  dragUid.value = null
  if (ruleId) emit('drop-rule', ruleId, uid)
}

/** 按区域 kind 生成装饰图形（仅视觉，几何随区域尺寸自适应） */
function decorItems(r: AnatomyRegion): DecItem[] {
  let items: DecItem[] = []
  const cx = r.x + r.w / 2
  const cy = r.y + r.h / 2
  switch (r.kind) {
    case 'bays': {
      const cols = Math.max(3, Math.min(4, Math.floor((r.w - 16) / 52)))
      const gap = 8
      const bayW = Math.min(44, (r.w - 16 - (cols - 1) * gap) / cols)
      const bayH = 84
      const rows = 3
      const totalW = cols * bayW + (cols - 1) * gap
      const totalH = rows * bayH + (rows - 1) * 12
      let y = cy - totalH / 2
      for (let row = 0; row < rows; row++) {
        let x = cx - totalW / 2
        for (let col = 0; col < cols; col++) {
          items.push({ type: 'rect', x, y, w: bayW, h: bayH, cls: 'dec-bay' })
          x += bayW + gap
        }
        y += bayH + 12
      }
      break
    }
    case 'cpus': {
      const sq = Math.min(74, Math.max(52, r.w * 0.2))
      const gap = 28
      const x1 = cx - sq - gap / 2
      const x2 = cx + gap / 2
      const y = cy - sq / 2
      items.push({ type: 'rect', x: x1, y, w: sq, h: sq, cls: 'dec-cpu', label: 'CPU1' })
      items.push({ type: 'rect', x: x2, y, w: sq, h: sq, cls: 'dec-cpu', label: 'CPU2' })
      const barW = 10
      const barH = 44
      const barGap = 6
      const n = 5
      let bx = cx - (n * barW + (n - 1) * barGap) / 2
      const by = r.y + 24
      for (let i = 0; i < n; i++) {
        items.push({ type: 'rect', x: bx, y: by, w: barW, h: barH, cls: 'dec-dimm' })
        bx += barW + barGap
      }
      break
    }
    case 'gpu': {
      const n = Math.max(3, Math.min(8, Math.floor((r.w - 24) / 38)))
      const gap = 8
      const cardW = Math.min(32, (r.w - 24 - (n - 1) * gap) / n)
      const cardH = Math.min(170, r.h - 64)
      const totalW = n * cardW + (n - 1) * gap
      const x0 = cx - totalW / 2
      for (let i = 0; i < n; i++) {
        items.push({ type: 'rect', x: x0 + i * (cardW + gap), y: cy - cardH / 2, w: cardW, h: cardH, cls: 'dec-gpu' })
      }
      break
    }
    case 'fans': {
      const cols = Math.max(1, Math.min(2, Math.floor(r.w / 52)))
      const rows = Math.max(2, Math.min(6, Math.floor((r.h - 30) / 58)))
      const rad = Math.min(20, (r.w - 20) / (2 * cols) - 3)
      const totalW = cols * rad * 2 + (cols - 1) * 12
      const totalH = rows * rad * 2 + (rows - 1) * 12
      let y = cy - totalH / 2 + rad
      for (let row = 0; row < rows; row++) {
        let x = cx - totalW / 2 + rad
        for (let col = 0; col < cols; col++) {
          items.push({ type: 'circle', cx: x, cy: y, r: rad, cls: 'dec-fan' })
          x += rad * 2 + 12
        }
        y += rad * 2 + 12
      }
      break
    }
    case 'psu': {
      const n = r.h >= 300 ? 2 : 4
      const gap = 12
      const pw = Math.min(72, r.w - 24)
      const ph = (r.h - gap * (n - 1) - 20) / n
      let y = r.y + 10
      for (let i = 0; i < n; i++) {
        items.push({ type: 'rect', x: cx - pw / 2, y, w: pw, h: ph, cls: 'dec-psu', label: 'PSU' })
        y += ph + gap
      }
      break
    }
    case 'io': {
      const n = r.h >= 300 ? 5 : 2
      const gap = 10
      const iw = Math.min(72, r.w - 20)
      const ih = (r.h - gap * (n - 1) - 20) / n
      let y = r.y + 10
      for (let i = 0; i < n; i++) {
        const label = n === 5 ? (i < 4 ? `IO${i + 1}` : 'OCP') : (i === 0 ? 'OCP' : 'PCIe')
        items.push({ type: 'rect', x: cx - iw / 2, y, w: iw, h: ih, cls: i === n - 1 ? 'dec-ocp' : 'dec-slot', label })
        y += ih + gap
      }
      break
    }
  }
  const sc = props.sandboxCounts || {}
  if (r.kind === 'gpu') return sliceDecor(items, 'dec-gpu', sc.gpu)
  if (r.kind === 'psu') return sliceDecor(items, 'dec-psu', sc.psu)
  if (r.kind === 'bays') return sliceDecor(items, 'dec-bay', sc.drives)
  if (r.kind === 'cpus') {
    items = sliceDecor(items, 'dec-cpu', sc.cpu)
    return sliceDecor(items, 'dec-dimm', sc.dimm)
  }
  return items
}

/** 沙盒截显：某类装饰元素只保留前 count 个（缺省不截） */
function sliceDecor(items: DecItem[], cls: string, count: number | undefined): DecItem[] {
  if (count == null) return items
  let seen = 0
  return items.filter(it => {
    if (it.cls !== cls) return true
    seen++
    return seen <= count
  })
}

</script>

<template>
  <div class="sam">
    <svg viewBox="0 0 1000 560" class="sam-svg" role="img" :aria-label="viewLabel">
      <rect class="sam-chassis" x="20" y="40" width="960" height="480" rx="16" />
      <text class="sam-side-label" x="42" y="32">{{ sideLabel }}</text>
      <text v-if="sideLabelEnd" class="sam-side-label" x="958" y="32" text-anchor="end">{{ sideLabelEnd }}</text>

      <g v-for="r in regions" :key="r.id" class="sam-region"
        :class="{ on: activeId === r.id, empty: decorMode !== 'plain' && !counts[r.id], hl: highlightIds.includes(r.id), dragOver: dragUid === r.id }"
        @click="$emit('select', activeId === r.id ? null : r.id, r)"
        @mouseenter="$emit('hover', r.id, r)"
        @mouseleave="$emit('hover', null, null)"
        @dragenter.prevent="dragUid = r.id"
        @dragleave.prevent="dragUid = null"
        @dragover.prevent
        @drop.prevent.stop="onDrop($event, r.id)">
        <title>{{ r.tip || `${r.name}（点击查看相关规则）` }}</title>

        <rect class="sam-region-bg" :x="r.x" :y="r.y" :width="r.w" :height="r.h" rx="10" />

        <g v-if="decorMode !== 'plain' && !counts[r.id] && activeId !== r.id" class="sam-norule">
          <rect class="sam-norule-bg" :x="r.x + 8" :y="r.y + 8" :width="r.w - 16" :height="r.h - 16" rx="6" />
        </g>

        <template v-for="(d, i) in decorItems(r)" :key="i">
          <rect v-if="d.type === 'rect'" :x="d.x" :y="d.y" :width="d.w" :height="d.h" rx="5" :class="d.cls" />
          <circle v-else :cx="d.cx" :cy="d.cy" :r="d.r" :class="d.cls" />
          <text v-if="d.label" class="sam-dec-label" :x="(d.x ?? d.cx!) + (d.w ?? 0) / 2" :y="(d.y ?? d.cy!) + (d.h ?? 0) / 2 + 5" text-anchor="middle">{{ d.label }}</text>
        </template>

        <text class="sam-name" :x="r.x + r.w / 2" :y="r.y + r.h - 16" text-anchor="middle">{{ r.name }}</text>

        <g v-if="decorMode !== 'plain'" class="sam-badge" :class="{ zero: !counts[r.id] }">
          <circle :cx="r.x + r.w - 16" :cy="r.y + 16" r="13" />
          <text :x="r.x + r.w - 16" :y="r.y + 21" text-anchor="middle">{{ badges?.[r.id] ?? (counts[r.id] || 0) }}</text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.sam { width: 100%; }
.sam-svg { width: 100%; height: auto; display: block; user-select: none; }
.sam-chassis {
  fill: rgba(255, 255, 255, 0.045);
  stroke: var(--cpq-glass-border);
  stroke-width: 1.5;
}
.sam-side-label { fill: var(--cpq-text-disabled); font-size: 13px; letter-spacing: 1px; }
.sam-region { cursor: pointer; }
.sam-region-bg {
  fill: rgba(255, 255, 255, 0.055);
  stroke: rgba(255, 255, 255, 0.14);
  stroke-width: 1;
  transition: fill 0.18s var(--cpq-ease-smooth), stroke 0.18s var(--cpq-ease-smooth), filter 0.18s var(--cpq-ease-smooth);
}
.sam-region:hover .sam-region-bg {
  fill: rgba(22, 119, 255, 0.16);
  stroke: var(--cpq-accent-primary);
  filter: drop-shadow(0 0 6px rgba(22, 119, 255, 0.35));
}
.sam-region.on .sam-region-bg {
  fill: rgba(22, 119, 255, 0.26);
  stroke: var(--cpq-accent-primary);
  stroke-width: 1.6;
  filter: drop-shadow(0 0 8px rgba(22, 119, 255, 0.45));
}
.sam-region.hl .sam-region-bg {
  fill: rgba(52, 211, 153, 0.18);
  stroke: #34d399;
  stroke-width: 1.8;
  filter: drop-shadow(0 0 8px rgba(52, 211, 153, 0.4));
}
.sam-region.hl .sam-name { fill: #d1fae5; }
.sam-region.empty .sam-region-bg {
  fill: rgba(255, 255, 255, 0.03);
  stroke: rgba(255, 255, 255, 0.08);
  stroke-dasharray: 6 5;
}
.sam-norule-bg { fill: rgba(0, 0, 0, 0.18); stroke: rgba(255, 255, 255, 0.06); stroke-dasharray: 4 4; }
.sam-dec-label { fill: rgba(255, 255, 255, 0.55); font-size: 11px; pointer-events: none; }
.sam-name { fill: var(--cpq-text-primary); font-size: 15px; font-weight: 600; pointer-events: none; }
.sam-region.empty .sam-name { fill: var(--cpq-text-disabled); }
.sam-region.on .sam-name { fill: #fff; }
.dec-bay, .dec-cpu, .dec-dimm, .dec-gpu, .dec-fan, .dec-psu, .dec-slot, .dec-ocp {
  fill: rgba(255, 255, 255, 0.13);
  stroke: rgba(255, 255, 255, 0.1);
  stroke-width: 1;
  pointer-events: none;
}
.sam-region.on .dec-bay, .sam-region.on .dec-cpu, .sam-region.on .dec-dimm,
.sam-region.on .dec-gpu, .sam-region.on .dec-fan, .sam-region.on .dec-psu,
.sam-region.on .dec-slot, .sam-region.on .dec-ocp { fill: rgba(255, 255, 255, 0.22); }
.dec-gpu { stroke: rgba(168, 85, 247, 0.55); }
.dec-ocp { fill: rgba(22, 119, 255, 0.22); stroke: var(--cpq-accent-primary); }
.sam-badge { pointer-events: none; }
.sam-badge circle {
  fill: var(--cpq-accent-primary);
  stroke: rgba(255, 255, 255, 0.35);
  stroke-width: 1;
}
.sam-badge text { fill: #fff; font-size: 12px; font-weight: 700; }
.sam-badge.zero { opacity: 0.55; }
.sam-badge.zero circle { fill: var(--cpq-bg-tertiary); stroke: rgba(255, 255, 255, 0.2); }
.sam-badge.zero text { fill: var(--cpq-text-disabled); }
.sam-region.dragOver .sam-region-bg { stroke: #38bdf8; stroke-width: 2.5; filter: drop-shadow(0 0 6px rgba(56, 189, 248, 0.8)); }


</style>
