<template>
  <div class="am-row" :class="`role-${role}`">
    <template v-if="role !== 'user'">
      <div
        class="am-avatar"
        :class="{ 'am-avatar-has-img': !!author.avatar_url }"
        :style="{ background: author.color || 'var(--cpq-accent-primary, #1677ff)' }"
      >
        <img v-if="author.avatar_url" :src="author.avatar_url" alt="" />
        <span v-else class="am-avatar-initial">{{ avatarInitial(author.name) }}</span>
      </div>
      <div class="am-content">
        <span v-if="author.name" class="am-author">{{ author.name }}</span>
        <div v-if="thinkingActive" class="am-thinking" :class="{ 'am-thinking--collapsed': thinkingCollapsed }">
          <button type="button" class="am-thinking-head" @click="thinkingCollapsed = !thinkingCollapsed">
            <span class="am-thinking-icon">💭</span>
            <span class="am-thinking-label">思考过程</span>
            <span v-if="!thinking" class="am-thinking-wait">正在思考</span>
            <span v-else class="am-thinking-collapse">{{ thinkingCollapsed ? '展开' : '收起' }}</span>
          </button>
          <div v-if="!thinkingCollapsed && thinking" class="am-thinking-body">
            {{ thinking }}<span v-if="thinking && !content" class="am-cursor">▍</span>
          </div>
        </div>
        <div class="am-bubble">
          <template v-if="typing">
            <span class="am-typing"><i></i><i></i><i></i></span>
            <span v-if="statusText" class="am-status">{{ statusText }}</span>
          </template>
          <template v-else>{{ content }}<span v-if="streaming" class="am-cursor">▍</span></template>
        </div>
        <div v-if="optionGroups.length" class="am-options">
          <div v-for="group in optionGroups" :key="group.slot" class="am-option-group">
            <span v-if="group.label" class="am-option-group-label">{{ group.label }}</span>
            <button
              v-for="opt in group.options"
              :key="opt.value"
              type="button"
              class="am-option-chip"
              @click="emit('select-option', opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="am-bubble">{{ content }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  message?: {
    role?: string
    content?: string
    kind?: string
    data?: string
  }
  author?: {
    name?: string
    avatar_url?: string
    color?: string
  }
  streaming?: boolean
  typing?: boolean
  statusText?: string
  thinking?: string
  thinkingActive?: boolean
}>(), {
  message: undefined,
  author: () => ({ name: 'AI', avatar_url: '', color: '' }),
  streaming: false,
  typing: false,
  statusText: '',
  thinking: '',
  thinkingActive: false,
})

const emit = defineEmits<{ (e: 'select-option', value: string): void }>()

const thinkingCollapsed = ref(false)
const role = computed(() => props.message?.role === 'user' ? 'user' : 'assistant')
const content = computed(() => props.message?.content || '')

const optionGroups = computed<Array<{ slot: string; label: string; options: Array<{ label: string; value: string }> }>>(() => {
  if (props.message?.kind !== 'input_options' || !props.message?.data) return []
  try {
    const data = JSON.parse(props.message.data)
    const slotOptions: Record<string, Array<{ label?: string; value?: string; group?: string }>> = data?.slot_options || {}
    const groups = Object.entries(slotOptions)
      .map(([slot, opts]) => {
        const arr = Array.isArray(opts) ? opts : []
        const options = arr.map((o: any) => ({
          label: String(o?.label ?? o?.value ?? ''),
          value: String(o?.value ?? o?.label ?? ''),
        })).filter((o: { label: string; value: string }) => o.label)
        const groupLabel = String(arr.find((o: any) => o?.group)?.group || '')
        return { slot, label: groupLabel, options }
      })
      .filter((g) => g.options.length)
    if (groups.length) return groups
    const flat = Array.isArray(data?.options) ? data.options : []
    const options = flat.map((o: any) => ({
      label: String(o?.label ?? o ?? ''),
      value: String(o?.value ?? o?.label ?? o ?? ''),
    })).filter((o: { label: string; value: string }) => o.label)
    return options.length ? [{ slot: 'general', label: '', options }] : []
  } catch {
    return []
  }
})

function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}
</script>

<style scoped>
.am-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.role-user {
  justify-content: flex-end;
}

.role-assistant,
.role-system {
  justify-content: flex-start;
}

.am-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677ff);
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
}

.am-avatar-initial {
  line-height: 1;
}

.am-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.am-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  max-width: calc(100% - 38px);
}

.am-author {
  font-size: 12px;
  line-height: 1.2;
  color: var(--cpq-text-muted);
  margin-bottom: 4px;
}

.am-thinking {
  margin-bottom: 6px;
  border-radius: 8px;
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  border: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.12));
  overflow: hidden;
  max-width: 82%;
}

.am-thinking--collapsed .am-thinking-body {
  display: none;
}

.am-thinking-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 10px;
  border: 0;
  background: transparent;
  font-size: 12px;
  color: var(--cpq-text-muted, #8c8c8c);
  cursor: pointer;
  text-align: left;
}

.am-thinking-icon {
  font-size: 12px;
}

.am-thinking-label {
  font-weight: 500;
  color: var(--cpq-text-secondary, #a6adb4);
}

.am-thinking-wait {
  color: var(--cpq-text-muted, #8c8c8c);
}

.am-thinking-wait::after {
  content: '…';
  animation: am-blink 1s steps(2, start) infinite;
}

.am-thinking-collapse {
  margin-left: auto;
  font-size: 11px;
  color: var(--cpq-text-muted, #8c8c8c);
}

.am-thinking-body {
  padding: 0 10px 8px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--cpq-text-secondary, #a6adb4);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow-y: auto;
}

.am-bubble {
  max-width: 82%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}

.role-user .am-bubble {
  background: var(--cpq-accent-primary, #1677ff);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.role-assistant .am-bubble,
.role-system .am-bubble {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-primary);
  border: 1px solid var(--cpq-overlay-w6);
  border-bottom-left-radius: 4px;
}

.am-cursor {
  display: inline-block;
  animation: am-blink 1s steps(2, start) infinite;
  color: var(--cpq-accent-primary, #1677ff);
  margin-left: 1px;
}

@keyframes am-blink {
  to { visibility: hidden; }
}

.am-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.am-option-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.am-option-group-label {
  min-width: 68px;
  font-size: 12px;
  color: var(--cpq-text-muted, #8c8c8c);
}
.am-option-chip {
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.12));
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--cpq-text-secondary, #a6adb4);
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease, background .15s ease;
}
.am-option-chip:hover {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-a8, rgba(22,119,255,.10));
}

.am-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
}

.am-status {
  margin-left: 8px;
  font-size: 12px;
  color: var(--cpq-text-muted, #8c8c8c);
  white-space: nowrap;
}

.am-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  animation: am-typing-bounce 1.2s infinite ease-in-out;
}

.am-typing i:nth-child(2) { animation-delay: 0.15s; }
.am-typing i:nth-child(3) { animation-delay: 0.3s; }

@keyframes am-typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
  30% { transform: translateY(-3px); opacity: 1; }
}
</style>