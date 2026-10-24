<template>
  <a-popover trigger="click" placement="bottomRight" overlay-class-name="online-pill-popover">
    <button type="button" class="online-pill" title="在线成员">
      <span class="online-dot" :class="{ dim: !onlineCount }" />
      <span class="online-label">{{ onlineCount }} 人在线</span>
    </button>
    <template #content>
      <div class="online-panel">
        <div class="online-head">
          <span class="online-title">成员</span>
          <span class="online-sub">在线 {{ onlineCount }} / {{ onlineUsers.length }}</span>
        </div>
        <div class="online-list">
          <div v-if="!onlineUsers.length" class="online-empty">暂无成员</div>
          <div v-for="u in onlineUsers" :key="u.user_id" class="online-item" :class="{ off: !u.online }">
            <span class="online-item-dot" />
            <span class="online-item-name">{{ u.name }}</span>
            <span v-if="u.user_id === selfId" class="online-item-self">我</span>
            <span class="online-item-role">{{ u.role_name }}</span>
          </div>
        </div>
      </div>
    </template>
  </a-popover>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useNotifications } from '@/composables/useNotifications'
import { useAuthStore } from '@/store/auth'

const { onlineUsers, start } = useNotifications()
const auth = useAuthStore()
start()

const onlineCount = computed(() => onlineUsers.value.filter((u) => u.online).length)
const selfId = computed(() => auth.user?.user_id || '')
</script>

<style scoped>
/* 胶囊样式自带：父组件的 .action-pill 是 scoped 样式，透不进 popover 触发器，必须在此完整定义 */
.online-pill {
  appearance: none;
  outline: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 12px;
  border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-border-secondary);
  background: var(--cpq-overlay-w5);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition:
    color var(--cpq-dur-1) var(--cpq-ease-smooth),
    border-color var(--cpq-dur-1) var(--cpq-ease-smooth),
    background var(--cpq-dur-1) var(--cpq-ease-smooth),
    transform var(--cpq-dur-2) var(--cpq-ease-out-expo);
}
.online-pill:hover {
  color: var(--cpq-text-primary);
  border-color: var(--cpq-glass-border-strong);
  background: var(--cpq-overlay-a8);
  transform: translateY(-1px);
}
.online-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--cpq-color-success);
  box-shadow: var(--cpq-led-active-glow);
}
.online-dot.dim {
  background: var(--cpq-text-quaternary);
  box-shadow: none;
}
.online-label {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 手机端隐藏：在线人数对移动用户无操作价值，给窄顶栏腾位置（2026-10-21） */
@media (max-width: 768px) {
  .online-pill { display: none; }
}
.online-panel {
  width: 264px;
  display: flex;
  flex-direction: column;
  margin: -4px -8px;
}
.online-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 6px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}
.online-title {
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-size: 14px;
}
.online-sub {
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.online-list {
  max-height: 320px;
  overflow-y: auto;
  padding: 4px 0 6px;
}
.online-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}
.online-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
}
.online-item:hover {
  background: var(--cpq-overlay-a4, rgba(22, 119, 255, 0.04));
}
.online-item-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-color-success);
  flex-shrink: 0;
}
.online-item.off .online-item-dot {
  background: var(--cpq-text-quaternary);
}
.online-item.off .online-item-name,
.online-item.off .online-item-role {
  opacity: 0.45;
}
.online-item-name {
  font-size: 13px;
  color: var(--cpq-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.online-item-self {
  flex-shrink: 0;
  font-size: 10.5px;
  color: var(--cpq-accent-primary);
  border: 1px solid currentColor;
  border-radius: var(--cpq-radius-xs);
  padding: 0 4px;
  line-height: 1.5;
}
.online-item-role {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--cpq-text-secondary);
  background: var(--cpq-bg-secondary);
  border-radius: var(--cpq-radius-xs);
  padding: 1px 7px;
}
</style>

<style>
/* popover 浮层挂在 body 下，需全局覆盖内边距 */
.online-pill-popover .ant-popover-inner-content {
  padding: 8px;
}
</style>
