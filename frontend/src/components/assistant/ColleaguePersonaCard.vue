<template>
  <Teleport to="body">
    <div v-if="visible" ref="pcardEl" class="pcard" :style="posStyle" @mousedown.stop>
      <div class="pc-head">
        <div class="pc-avatar" :style="{ background: colleague?.color || 'var(--cpq-accent-primary, #1677ff)' }">
          <img v-if="colleague?.avatar_url" :src="colleague.avatar_url" alt="" />
          <span v-else>{{ initial }}</span>
        </div>
        <div class="pc-id">
          <div class="pc-name">
            {{ colleague?.name || colleague?.role_key || 'AI 同事' }}
            <span v-if="colleague?.role_key === leadRoleKey" class="pc-lead" title="团队 Lead">Lead</span>
          </div>
          <div class="pc-role">{{ colleague?.role_key }}</div>
        </div>
        <span class="pc-status" :style="statusStyle">{{ statusLabel }}</span>
      </div>

      <div class="pc-bio">{{ description }}</div>

      <div v-if="mission" class="pc-mission" @click="$emit('task', colleague?.role_key)">
        <span class="pc-mission-k">手头任务</span>
        <span class="pc-mission-v">{{ mission.prompt }}</span>
      </div>

      <div v-if="toolChips.length" class="pc-tools">
        <span v-for="t in toolChips" :key="t" class="pc-chip">{{ t }}</span>
        <span v-if="toolRest > 0" class="pc-chip pc-chip--more">+{{ toolRest }}</span>
      </div>

      <div class="pc-actions">
        <button type="button" class="pc-btn pc-btn--primary" @click="$emit('dm', colleague?.role_key)">发私聊</button>
        <button v-if="taskAction" type="button" class="pc-btn" @click="$emit('task', colleague?.role_key)">看任务</button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{
  /** 行为配置里的状态文案表（status → label/color），办公室页直接下发 */
  statusMeta?: Record<string, { label?: string; color?: string }>
  leadRoleKey?: string
  /** 显示「看任务」按钮（办公室页有任务板才开；聊天窗口里没板可看，默认关） */
  taskAction?: boolean
}>()

defineEmits<{
  (e: 'dm', roleKey?: string): void
  (e: 'task', roleKey?: string): void
}>()

const visible = ref(false)
const colleague = ref<any>(null)
const status = ref<{ status?: string; activity?: string } | null>(null)
const mission = ref<{ prompt?: string } | null>(null)
const posStyle = ref<Record<string, string>>({})
const pcardEl = ref<HTMLElement | null>(null)
/** 触发元素：外点关闭时放行它（点同一头像交给 openFor 翻面收起） */
let anchorEl: HTMLElement | null = null

function openFor(c: any, st: { status?: string; activity?: string } | null, m: { prompt?: string } | null, anchor?: HTMLElement | null) {
  // 同一触发元素再点同一同事 = 收起（toggle）
  if (visible.value && anchor && anchor === anchorEl && colleague.value?.role_key === c?.role_key) {
    close()
    return
  }
  colleague.value = c
  status.value = st
  mission.value = m
  visible.value = true
  anchorEl = anchor || null
  const r = anchor?.getBoundingClientRect()
  const width = 300
  let x = Math.max(8, Math.min((window.innerWidth || 1200) - width - 8, (r?.left ?? 100) as number))
  let y = (r?.bottom ?? 100) + 8
  // 先挂载再量高：下一帧夹回视口
  requestAnimationFrame(() => {
    const h = pcardEl.value?.getBoundingClientRect().height || 260
    if (y + h > (window.innerHeight || 800) - 8) y = Math.max(8, (r?.top ?? 100) - h - 8)
    posStyle.value = { left: `${x}px`, top: `${y}px`, width: `${width}px` }
  })
  posStyle.value = { left: `${x}px`, top: `${y}px`, width: `${width}px` }
}
function close() {
  visible.value = false
}

function onDocPointerDown(e: PointerEvent) {
  if (!visible.value) return
  const t = e.target as Node | null
  if (!t) return
  if (pcardEl.value?.contains(t)) return
  if (anchorEl && anchorEl.contains(t)) return
  close()
}
function onWinScroll() {
  if (visible.value) close()
}
function onEscKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && visible.value) close()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocPointerDown, true)
  window.addEventListener('scroll', onWinScroll, true)
  window.addEventListener('keydown', onEscKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  window.removeEventListener('scroll', onWinScroll, true)
  window.removeEventListener('keydown', onEscKey)
})
defineExpose({ openFor, close })

const initial = computed(() => {
  const text = String(colleague.value?.name || colleague.value?.role_key || 'AI').trim()
  return Array.from(text)[0] || 'AI'
})
const description = computed(() => {
  const c = colleague.value
  if (!c) return 'AI 同事'
  if (typeof c.description === 'string' && c.description.trim()) return c.description.trim()
  const caps = Array.isArray(c.capabilities) ? c.capabilities : []
  const capText = caps.map((x: any) => (typeof x === 'string' ? x : x?.label || x?.name || '')).filter(Boolean).join('、')
  if (capText) return capText
  return 'AI 同事'
})
const statusLabel = computed(() => {
  const s = String(status.value?.status || '')
  return props.statusMeta?.[s]?.label || s || '空闲'
})
const statusStyle = computed(() => {
  const s = String(status.value?.status || '')
  const color = props.statusMeta?.[s]?.color || '#9aa4b2'
  return { color, borderColor: color, background: `${color}1a` }
})
const toolChips = computed(() => {
  const ids = Array.isArray(colleague.value?.tool_ids) ? colleague.value.tool_ids : []
  return ids.slice(0, 4).map((t: any) => String(t))
})
const toolRest = computed(() => {
  const ids = Array.isArray(colleague.value?.tool_ids) ? colleague.value.tool_ids : []
  return Math.max(0, ids.length - 4)
})
</script>

<style scoped>
.pcard {
  position: fixed;
  /* 浮动面板本体 1500+（全屏态 1600），名片必须压过它，否则开了也被面板盖住（曾用 1100 被吞） */
  z-index: 2000;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, 0.92));
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 18px 44px var(--cpq-shadow-color-strong, rgba(22, 119, 255, 0.14));
  padding: 14px;
}
.pc-head { display: flex; align-items: center; gap: 10px; }
.pc-avatar {
  width: 44px; height: 44px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 18px; font-weight: 600; overflow: hidden;
}
.pc-avatar img { width: 100%; height: 100%; object-fit: cover; }
.pc-id { flex: 1; min-width: 0; }
.pc-name { font-size: 15px; font-weight: 700; display: flex; align-items: center; gap: 6px; }
.pc-lead {
  font-size: 10px; font-weight: 700; letter-spacing: 1px;
  color: var(--cpq-accent-primary, #1677ff);
  border: 1px solid color-mix(in srgb, var(--cpq-accent-primary, #1677ff) 35%, transparent);
  padding: 0 6px; border-radius: var(--cpq-radius-full);
}
.pc-role { font-size: 12px; color: var(--cpq-text-muted, #86909c); margin-top: 2px; }
.pc-status {
  flex-shrink: 0; font-size: 12px; padding: 3px 10px; border-radius: var(--cpq-radius-full); border: 1px solid transparent;
}
.pc-bio { font-size: 12.5px; line-height: 1.7; color: var(--cpq-text-secondary); margin: 10px 0; }
.pc-mission {
  display: flex; gap: 8px; align-items: baseline; padding: 8px 10px; margin-bottom: 10px;
  border-radius: var(--cpq-radius-md); cursor: pointer;
  background: var(--cpq-overlay-w4, rgba(22, 119, 255, 0.04));
  border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
}
.pc-mission:hover { border-color: var(--cpq-glass-border-strong, rgba(22, 119, 255, 0.45)); }
.pc-mission-k { flex-shrink: 0; font-size: 11px; color: var(--cpq-text-muted, #86909c); }
.pc-mission-v { font-size: 12.5px; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-tools { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.pc-chip {
  font-size: 11px; padding: 2px 9px; border-radius: var(--cpq-radius-full);
  color: var(--cpq-accent-primary, #1677ff);
  background: color-mix(in srgb, var(--cpq-accent-primary, #1677ff) 11%, transparent);
}
.pc-chip--more { color: var(--cpq-text-muted, #86909c); background: var(--cpq-overlay-w4, rgba(22, 119, 255, 0.04)); }
.pc-actions { display: flex; gap: 8px; }
.pc-btn {
  flex: 1; text-align: center; padding: 7px 0; border-radius: var(--cpq-radius-sm); font-size: 12.5px;
  cursor: pointer; font-weight: 600; border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  color: var(--cpq-text-secondary); background: transparent; transition: all 0.15s;
}
.pc-btn:hover { border-color: var(--cpq-accent-primary, #1677ff); color: var(--cpq-accent-primary, #1677ff); }
.pc-btn--primary {
  background: var(--cpq-accent-gradient, linear-gradient(135deg, #1677FF 0%, #5B8FF9 100%));
  color: #fff; border: none;
  box-shadow: 0 3px 10px rgba(22, 119, 255, 0.30);
}
.pc-btn--primary:hover { color: #fff; opacity: 0.92; }
</style>
