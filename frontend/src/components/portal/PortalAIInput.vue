<script setup lang="ts">
/**
 * 门户 AI 入口（空闲态）：欢迎语 + 快捷磁贴 + 输入框。
 * 发送首条消息后 emit('open')，由 Portal 切换为聊天态（复用浮动窗口 AssistantPanel）。
 * 门户只保留这一处入口壳；聊天态交给 AssistantPanel 统一渲染。
 */
import { ref, inject } from 'vue'
import { ExpandOutlined } from '@ant-design/icons-vue'
import { useAssistantContext } from '@/composables/assistantContext'
import { PORTAL_ASSISTANT_KEY } from '@/components/portal/portalAssistant'
import AssistantComposer from '@/components/assistant/AssistantComposer.vue'

const emit = defineEmits<{ (e: 'open'): void }>()

// 注入 Portal.vue 持有的唯一实例（与聊天态 AssistantPanel 共享同一会话状态）
const assistant = inject(PORTAL_ASSISTANT_KEY, null)
if (!assistant) throw new Error('PortalAIInput 必须在 Portal.vue 内使用（缺少 provide）')
const { sending, running, send, stop } = assistant

const { summarize } = useAssistantContext()
const draft = ref('')
const composerRef = ref<InstanceType<typeof AssistantComposer> | null>(null)

async function onSend() {
  const text = draft.value
  if (!text.trim() || sending.value || running.value) return
  // 发送首条即进入聊天态：交还给 Portal 切换为完整聊天窗口
  emit('open')
  draft.value = ''
  const summary = await summarize()
  await send(text, summary)
}

async function onStop() {
  await stop()
}

function focus() {
  composerRef.value?.focus()
}
defineExpose({ focus })
</script>

<template>
  <!-- 居中限宽列容器：欢迎语 + 输入框 + 快捷磁贴，不铺满全屏 -->
  <div class="pai">
    <transition name="intro">
      <div class="pai-intro">
        <slot name="intro" />
      </div>
    </transition>

    <div class="pai-composer">
      <AssistantComposer
        ref="composerRef"
        v-model="draft"
        placeholder="配台 Orion 2U 50 台，内存 256G… / 查我的商机 / 帮我核价"
        :disabled="sending || running"
        :sending="sending"
        :running="running"
        :members="[]"
        :skills="[]"
        :show-skills="false"
        :context-usage="null"
        @send="onSend"
        @stop="onStop"
      >
        <template #actions>
          <button type="button" class="ac-expand-btn" title="展开聊天窗" @click="emit('open')">
            <ExpandOutlined />
            <span>展开</span>
          </button>
        </template>
      </AssistantComposer>
    </div>

    <transition name="intro">
      <div class="pai-below">
        <slot name="below" />
      </div>
    </transition>
  </div>
</template>

<style scoped>
.pai {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  height: 100%;
  min-height: 0;
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  padding: 0 20px;
  position: relative;
}
.pai-intro {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}
.pai-composer {
  width: 100%;
  flex-shrink: 0;
}
.pai-below {
  width: 100%;
  margin-top: 28px;
  flex-shrink: 0;
}

/* 展开按钮（发送旁入口：点击展开完整聊天窗，不发消息） */
.ac-expand-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w5);
  border: 1px solid var(--cpq-glass-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.ac-expand-btn:hover {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
}

/* 欢迎语/磁贴淡入 */
.intro-enter-active, .intro-leave-active {
  transition: opacity 0.24s ease, transform 0.24s ease;
}
.intro-enter-from, .intro-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
