<script setup lang="ts">
/** 服务器3D配置台薄壳 — 场景逻辑全在 server3d/(纯TS),本组件只做挂载/props桥接/HUD。
 *  counts 由父级(配置页 BOM)实时驱动:GPU/CPU/内存/盘位数量变化即插拔动画;
 *  theme='auto' 时跟随 html[data-theme],也可显式指定。 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createServerStage, type StageView } from '@/server3d/stage'

const props = withDefaults(defineProps<{
  counts?: { gpus?: number; cpus?: number; dimms?: number; bays?: number }
  /** 主题:'auto'=观察 html[data-theme];或显式 'light' / 'dark' */
  theme?: 'auto' | 'light' | 'dark'
  height?: string
  /** 分区标注覆盖(layout_config.labels):key=drives/ears/fans/cpu/gpus/psu/pcie,三行均可覆盖 */
  labels?: Record<string, { name?: string; spec?: string; desc?: string }>
  /** 部件模型:'cpu'/'fan' 时舞台上对应部件替代整机(部件库模型页用) */
  partType?: 'cpu' | 'fan' | null
  /** 部件参数(layout_config 解析):如 { family:'kh' } 切兆芯形态族 */
  partSpec?: { family?: 'sp5' | 'kh' } | null
  /** 整机处理器封装族:sp5=AMD(默认);kh=兆芯。品牌即参数,同一份资产按机型 series 切换 */
  cpuFamily?: 'sp5' | 'kh' | null
}>(), { counts: () => ({}), theme: 'auto', height: '380px' })

const host = ref<HTMLDivElement | null>(null)
const tip = ref<{ x: number; y: number; name: string; spec: string; desc: string } | null>(null)
let stage: ReturnType<typeof createServerStage> | null = null
let mo: MutationObserver | null = null

function currentTheme(): 'light' | 'dark' {
  if (props.theme !== 'auto') return props.theme
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

onMounted(() => {
  if (!host.value) return
  stage = createServerStage(host.value, undefined, { partType: props.partType ?? undefined, partSpec: props.partSpec ?? undefined, cpuFamily: props.cpuFamily ?? undefined })
  stage.applyTheme(currentTheme())
  stage.setOnHover((k) => {
    if (!k || !stage) { tip.value = null; return }
    const info = (stage.machine as any).PART_INFO[k]
    if (!info) { tip.value = null; return }
    const over = props.labels?.[k] || {}
    tip.value = {
      x: tipPos.value.x, y: tipPos.value.y,
      name: (over.name || '').trim() || info.name,
      spec: (over.spec || '').trim() || info.spec,
      desc: (over.desc || '').trim() || info.desc,
    }
  })
  stage.machine.setCounts(props.counts)
  // 调试句柄(控制台排障用,同 office3d 的 officeDebug 惯例)
  ;(window as any).__s3dStage = stage
  mo = new MutationObserver(() => stage?.applyTheme(currentTheme()))
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})

watch(() => props.counts, (c) => stage?.machine.setCounts(c || {}), { deep: true })
watch(() => props.theme, () => stage?.applyTheme(currentTheme()))
watch(() => [props.partType, props.partSpec, props.cpuFamily], () => {
  // 部件类型/形态族/整机CPU品牌变化=重建舞台(工厂在创建时定型)
  stage?.dispose()
  stage = null
  if (host.value) {
    stage = createServerStage(host.value, undefined, { partType: props.partType ?? undefined, partSpec: props.partSpec ?? undefined, cpuFamily: props.cpuFamily ?? undefined })
    stage.applyTheme(currentTheme())
    ;(window as any).__s3dStage = stage // 调试句柄跟随重建(否则指向已 dispose 的旧舞台)
  }
})

onBeforeUnmount(() => {
  mo?.disconnect()
  stage?.dispose()
  stage = null
})

const views: { key: StageView; label: string }[] = [
  { key: 'front', label: '正面' },
  { key: 'rear', label: '背面' },
  { key: 'top', label: '俯视' },
  { key: 'inner', label: '内部' },
]
const exploded = ref(false)
const autoRotate = ref(true)
const tipPos = ref({ x: 0, y: 0 })
function onHostMove(e: MouseEvent) {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  tipPos.value = { x: e.clientX - rect.left + 14, y: e.clientY - rect.top + 14 }
}
function toggleExplode() {
  exploded.value = !exploded.value
  stage?.setExploded(exploded.value)
}
function toggleRotate() {
  autoRotate.value = !autoRotate.value
  stage?.setAutoRotate(autoRotate.value)
}
function fly(v: StageView) { stage?.flyTo(v) }
</script>

<template>
  <div class="s3d-wrap" :style="{ height }" @mousemove="onHostMove">
    <div ref="host" class="s3d-host"></div>
    <div class="s3d-hud">
      <button v-for="v in views" :key="v.key" class="s3d-btn" @click="fly(v.key)">{{ v.label }}</button>
      <span class="s3d-hud-sep"></span>
      <button class="s3d-btn" :class="{ on: exploded }" @click="toggleExplode">爆炸视图</button>
      <button class="s3d-btn" :class="{ on: autoRotate }" @click="toggleRotate">自动旋转</button>
    </div>
    <div v-if="tip" class="s3d-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      <b>{{ tip.name }}</b>
      <span>{{ tip.spec }}</span>
      <span v-if="tip.desc" class="s3d-tip-desc">{{ tip.desc }}</span>
    </div>
  </div>
</template>

<style scoped>
.s3d-wrap {
  position: relative;
  width: 100%;
  min-height: 240px;
  overflow: hidden;
  border-radius: var(--cpq-radius-md);
}
.s3d-host {
  position: absolute;
  inset: 0;
}
.s3d-host :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
}
.s3d-hud {
  position: absolute;
  bottom: var(--cpq-space-3);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--cpq-space-1);
  flex-wrap: wrap;
  max-width: calc(100% - var(--cpq-space-4));
}
.s3d-hud-sep {
  width: 1px;
  height: 14px;
  background: var(--cpq-overlay-w10);
}
.s3d-btn {
  appearance: none;
  border: 1px solid var(--cpq-overlay-w10);
  background: var(--cpq-overlay-b40);
  color: var(--cpq-text-primary);
  font-size: var(--cpq-font-size-xs);
  padding: 2px 8px;
  border-radius: var(--cpq-radius-sm);
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: border-color 0.18s ease, background 0.18s ease;
}
.s3d-btn:hover {
  border-color: var(--cpq-accent-primary);
}
.s3d-btn.on {
  background: color-mix(in srgb, var(--cpq-accent-primary) 30%, transparent);
  border-color: var(--cpq-accent-primary);
}
.s3d-tip {
  position: absolute;
  z-index: 3;
  pointer-events: none;
  max-width: 250px;
  padding: var(--cpq-space-1) var(--cpq-space-2);
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--cpq-overlay-b40);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm);
  backdrop-filter: blur(10px);
  color: var(--cpq-text-primary);
  font-size: var(--cpq-font-size-xs);
  line-height: 1.5;
}
.s3d-tip b {
  color: var(--cpq-accent-primary);
}
.s3d-tip-desc {
  color: var(--cpq-text-secondary);
}
</style>
