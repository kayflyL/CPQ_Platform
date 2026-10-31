<template>
  <Teleport to="body">
    <Transition name="office-fade">
      <div
        v-if="colleague"
        class="ohc"
        :style="posStyle"
        @mouseenter="emit('keep')"
        @mouseleave="emit('leave')"
      >
        <div class="ohc-head">
          <div class="ohc-av" :style="{ background: color }">
            <img v-if="colleague.avatar_url" :src="colleague.avatar_url" alt="" />
            <span v-else>{{ initial }}</span>
          </div>
          <div class="ohc-id">
            <div class="ohc-name">{{ colleague.name || colleague.role_key }}</div>
            <div class="ohc-role">{{ colleague.role_key }}</div>
            <div class="ohc-status">
              <i :style="{ background: statusColor }"></i>
              <span>{{ statusText }}<template v-if="status.activity"> · {{ status.activity }}</template></span>
            </div>
          </div>
        </div>
        <div class="ohc-stats">
          <div><b class="num">{{ stats.active }}</b><span>进行中</span></div>
          <div><b class="num">{{ stats.done }}</b><span>已完成</span></div>
          <div><b class="num">{{ stats.total }}</b><span>近 20 条</span></div>
        </div>
        <div class="ohc-act">
          <button type="button" class="ohc-btn ohc-btn--chat" @click="emit('chat')">聊天</button>
          <button type="button" class="ohc-btn" @click="emit('profile', $event)">档案</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
/* 角色头顶悬停卡（对齐 workstation-teacher 的 hcard 契约）：
   悬停浮现 / 移开延迟隐藏 / 卡上保持；[聊天][档案] 双动作。
   定位由父组件传 x/y（指针锚点），组件内做防出屏钳制与上下翻转。 */
import { computed } from 'vue'
import type { OfficeColleagueStatus } from '@/api/office'

const props = defineProps<{
  colleague: any | null
  status: OfficeColleagueStatus
  stats: { active: number; done: number; total: number }
  color: string
  x: number
  y: number
}>()

const emit = defineEmits<{ (e: 'chat'): void; (e: 'profile', ev: MouseEvent): void; (e: 'keep'): void; (e: 'leave'): void }>()

const CARD_W = 300
const CARD_H = 232
const M = 12

const initial = computed(() => {
  const text = (props.colleague?.name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
})

const statusColor = computed(() => props.status?.status === 'working' ? 'var(--cpq-color-success)'
  : props.status?.status === 'error' ? 'var(--cpq-color-danger)'
    : 'var(--cpq-accent-primary)')

const statusText = computed(() => {
  const map: Record<string, string> = {
    working: '工作中', idle: '空闲', error: '异常',
  }
  return map[props.status?.status] || props.status?.activity || '空闲'
})

const posStyle = computed(() => {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const x = Math.min(Math.max(props.x - CARD_W / 2, M), Math.max(vw - CARD_W - M, M))
  const below = props.y + CARD_H + 48 < vh
  const y = below ? props.y + 18 : Math.max(props.y - CARD_H - 18, M)
  return { left: x + 'px', top: y + 'px' }
})
</script>

<style scoped>
.ohc {
  position: fixed; z-index: 950;
  width: 300px;
  padding: var(--cpq-space-4);
  border-radius: var(--cpq-radius-xl);
  background: var(--cpq-glass-3-bg-solid, rgba(20, 26, 40, 0.94));
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-glass-border-strong, rgba(22, 119, 255, 0.4));
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.5), inset 0 1px 0 var(--cpq-overlay-w15);
  animation: ohc-in var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
@keyframes ohc-in { from { opacity: 0; transform: translateY(6px); } }

.ohc-head { display: flex; gap: var(--cpq-space-3); align-items: center; }
.ohc-av {
  width: 44px; height: 44px; flex: none; border-radius: 50%;
  display: grid; place-items: center; overflow: hidden;
  color: var(--cpq-accent-on-primary); font-weight: 700; font-size: var(--cpq-font-size-lg);
}
.ohc-av img { width: 100%; height: 100%; object-fit: cover; }
.ohc-id { min-width: 0; flex: 1; }
.ohc-name { font-size: var(--cpq-font-size-lg); font-weight: 700; color: var(--cpq-text-primary); }
.ohc-role { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.ohc-status {
  display: flex; align-items: center; gap: 5px; margin-top: 3px;
  font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary);
}
.ohc-status i { width: 7px; height: 7px; border-radius: 50%; flex: none; }

.ohc-stats {
  display: grid; grid-template-columns: repeat(3, 1fr);
  margin-top: var(--cpq-space-3); padding: var(--cpq-space-2) 0;
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.04));
  border-radius: var(--cpq-radius-md); text-align: center;
}
.ohc-stats b { display: block; font-weight: 650; font-size: var(--cpq-font-size-base); color: var(--cpq-text-primary); }
.ohc-stats span { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }

.ohc-act { display: flex; gap: var(--cpq-space-2); margin-top: var(--cpq-space-3); }
.ohc-btn {
  flex: 1; height: 32px; border-radius: var(--cpq-radius-sm);
  background: var(--cpq-glass-2-bg); border: 1px solid var(--cpq-glass-border);
  color: var(--cpq-text-primary); font-size: var(--cpq-font-size-sm); font-weight: 600;
  transition: all var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.ohc-btn:hover { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }
.ohc-btn--chat {
  background: var(--cpq-accent-gradient); border: none; color: var(--cpq-accent-on-primary);
  box-shadow: 0 3px 10px var(--cpq-shadow-color-soft);
}
.ohc-btn--chat:hover { color: var(--cpq-accent-on-primary); filter: brightness(1.08); }
</style>
