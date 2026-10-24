<template>
  <Transition name="ih">
    <div
      v-if="shown"
      class="install-hint"
      :style="bottomOffset ? { bottom: bottomOffset } : undefined"
    >
      <span class="install-hint-text">把 CPQ 装成桌面 App,全屏无浏览器栏</span>
      <button type="button" class="install-hint-go" @click="goHelp">安装</button>
      <button type="button" class="install-hint-x" aria-label="不再提示" @click="dismiss">
        <CloseOutlined />
      </button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
// 移动端「安装为桌面 App」引导入口:仅在手机浏览器的网页模式出现;
// 已安装(display-mode: standalone / iOS navigator.standalone)或手动关闭过(localStorage)则不出现。
// 登录页与主布局壳共用本组件;底栏高度由使用方经 bottom-offset 传入。
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { CloseOutlined } from '@ant-design/icons-vue'

const props = defineProps<{ bottomOffset?: string }>()
const shown = ref(false)
const isMobile = ref(false)
let mqListener: ((e: MediaQueryListEvent) => void) | null = null

onMounted(() => {
  const mq = window.matchMedia('(max-width: 768px)')
  isMobile.value = mq.matches
  mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', mqListener)

  const standalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  let off = false
  try { off = localStorage.getItem('cpq-install-hint-off') === '1' } catch {}
  shown.value = isMobile.value && !standalone && !off
})
onBeforeUnmount(() => {
  if (mqListener) window.matchMedia('(max-width: 768px)').removeEventListener('change', mqListener)
})

function dismiss() {
  shown.value = false
  try { localStorage.setItem('cpq-install-hint-off', '1') } catch {}
}
function goHelp() { window.location.href = '/install-help.html' }
</script>

<style scoped>
/* 玻璃胶囊,浮在视口底部;bottom 可被 bottomOffset 覆盖 */
.install-hint {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  z-index: 2100;
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2, 8px);
  padding: var(--cpq-space-2, 8px) var(--cpq-space-2, 8px) var(--cpq-space-2, 8px) var(--cpq-space-4, 16px);
  border-radius: var(--cpq-radius-full);
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, 0.72));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3, 20px)) saturate(1.35);
  backdrop-filter: blur(var(--cpq-glass-blur-3, 20px)) saturate(1.35);
  border: 1px solid var(--cpq-border-secondary, rgba(22, 119, 255, 0.06));
  box-shadow: 0 12px 32px var(--cpq-shadow-color, rgba(15, 23, 42, 0.25));
  max-width: calc(100vw - 24px);
}
.install-hint-text {
  font-size: var(--cpq-font-size-sm, 12px);
  color: var(--cpq-text-secondary, #4e5969);
  white-space: nowrap;
}
.install-hint-go {
  border: none;
  cursor: pointer;
  border-radius: var(--cpq-radius-full);
  padding: 5px 14px;
  background: var(--cpq-accent-primary, #1677FF);
  color: var(--cpq-accent-on-primary, #fff);
  font-size: var(--cpq-font-size-sm, 12px);
  font-weight: var(--cpq-font-weight-medium, 500);
  flex: none;
}
.install-hint-x {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--cpq-text-muted, #86909c);
  display: inline-flex;
  align-items: center;
  padding: var(--cpq-space-1, 4px);
  flex: none;
}
.ih-enter-active,
.ih-leave-active {
  transition: opacity var(--cpq-transition-normal, 0.3s), transform var(--cpq-transition-normal, 0.3s);
}
.ih-enter-from,
.ih-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>

<style>
/* 编辑类全屏弹层（同事档案等 antd modal）打开时让位：横幅 z2100 会压在弹层 z1000 上 */
body.em-editor-modal-open .install-hint,
body.office-fullscreen-open .install-hint {
  display: none !important;
}
</style>
