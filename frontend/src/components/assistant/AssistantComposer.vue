<template>
  <div class="ac-composer">
    <div class="ac-row">
      <!-- 技能入口：私聊=当前角色绑定技能；群聊=全员技能并集。点击仅插入输入框（不直接发送） -->
      <span v-if="showSkills && skillOptions.length" class="ac-skill-anchor">
        <button
          type="button"
          class="ac-plus-btn"
          title="选择技能"
          :disabled="disabled"
          @click="skillOpen = !skillOpen"
        >
          +
        </button>
        <transition name="ac-mention">
          <div v-if="skillOpen" class="ac-skill-pop" @mousedown.prevent @click.stop>
            <div class="ac-skill-head">技能</div>
            <button
              v-for="s in skillOptions"
              :key="s.key"
              type="button"
              class="ac-skill-item"
              @click="pickSkill(s)"
            >
              <span class="ac-skill-name">{{ s.name || s.key }}</span>
              <span v-if="s.description" class="ac-skill-desc">{{ s.description }}</span>
            </button>
            <div v-if="!skillOptions.length" class="ac-skill-empty">暂无可用技能</div>
          </div>
        </transition>
      </span>
      <div class="ac-input-wrap">
        <a-textarea
          ref="taRef"
          :value="modelValue"
          :auto-size="{ minRows: 1, maxRows: 4 }"
          :placeholder="placeholder"
          :disabled="disabled"
          @update:value="$emit('update:modelValue', $event)"
          @press-enter="onEnter"
        />
        <!-- @ 点名补全：键入 @ 或点 @ 按钮触发（群聊点名，确定性路由） -->
        <transition name="ac-mention">
          <div v-if="mentionOpen && filteredMembers.length" class="ac-mention-pop">
            <div class="ac-mention-head">点名同事</div>
            <button
              v-for="m in filteredMembers"
              :key="m.role_key"
              type="button"
              class="ac-mention-item"
              @mousedown.prevent
              @click="pickMention(m)"
            >
              <span class="ac-mention-avatar" :style="{ background: m.color || 'var(--cpq-accent-primary, #1677ff)' }">
                {{ String(m.name || m.role_key || 'AI').slice(0, 1) }}
              </span>
              <span class="ac-mention-name">{{ m.name || m.role_key }}</span>
              <span class="ac-mention-desc">{{ memberDesc(m) }}</span>
            </button>
          </div>
        </transition>
      </div>
      <div class="ac-actions">
        <button
          v-if="members.length"
          type="button"
          class="ac-at-btn"
          title="点名同事（@）"
          :disabled="disabled"
          @click="insertAt"
        >
          @
        </button>
        <a-button
          type="primary"
          :disabled="disabled || (!busy && !modelValue.trim())"
          @click="busy ? $emit('stop') : $emit('send')"
        >
          {{ busy ? '停止' : buttonText }}
        </a-button>
        <!-- 门户等宿主可在发送旁加扩展动作（如「展开」）；不传则不渲染 -->
        <slot name="actions" />
      </div>
    </div>
    <!-- 上下文水位：细进度条 + xx%（绿→黄→红） -->
    <div v-if="contextUsage" class="ac-ctx" :class="'ac-ctx--' + ctxLevel">
      <div class="ac-ctx-track"><i class="ac-ctx-fill" :style="{ width: ctxPct + '%' }"></i></div>
      <span class="ac-ctx-num">上下文 {{ ctxPct }}%</span>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  disabled?: boolean
  sending?: boolean
  running?: boolean
  buttonText?: string
  /** 群成员名册（传入后启用 @ 点名补全） */
  members?: any[]
  /** 技能菜单项（私聊=当前角色绑定；群聊=全员技能并集） */
  skills?: any[]
  /** 是否显示技能入口（+） */
  showSkills?: boolean
  /** 上下文水位（{ ratio }），传入则显示水位条 */
  contextUsage?: { ratio?: number } | null
}>(), {
  placeholder: '输入消息…',
  disabled: false,
  sending: false,
  running: false,
  buttonText: '发送',
  members: () => [],
  skills: () => [],
  showSkills: false,
  contextUsage: null,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'pickSkill', skill: any): void
}>()

const busy = computed(() => props.sending || props.running)
const taRef = ref<{ focus?: (option?: any) => void } | null>(null)

// ── @ 点名补全：文本以 "@片段" 结尾时弹出候选 ──
const mentionQuery = ref<string | null>(null)
const mentionOpen = computed(() => mentionQuery.value !== null && filteredMembers.value.length > 0)

const filteredMembers = computed(() => {
  const q = (mentionQuery.value || '').toLowerCase()
  return (props.members || []).filter((m) => {
    if (m?.enabled === false) return false
    const name = String(m.name || m.role_key || '').toLowerCase()
    const key = String(m.role_key || '').toLowerCase()
    return !q || name.includes(q) || key.includes(q)
  })
})

watch(() => props.modelValue, (v) => {
  const match = /@([^\s@]*)$/.exec(v || '')
  mentionQuery.value = match ? match[1] : null
})

// ── 技能菜单：按 key 去重 ──
const skillOpen = ref(false)
const skillOptions = computed<any[]>(() => {
  const seen = new Set<string>()
  const out: any[] = []
  for (const s of props.skills || []) {
    const key = String(s?.key ?? s?.skill_key ?? s?.name ?? '').trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push({ key, name: String(s?.name || key), description: String(s?.description || '') })
  }
  return out
})

function pickSkill(skill: any) {
  skillOpen.value = false
  emit('pickSkill', skill)
}

// ── 上下文水位：细进度条 + xx%（绿→黄→红） ──
const ctxPct = computed(() => Math.round((props.contextUsage?.ratio || 0) * 100))
const ctxLevel = computed(() => (ctxPct.value >= 90 ? 'high' : ctxPct.value >= 70 ? 'warn' : 'ok'))

function memberDesc(m: any): string {
  if (typeof m?.description === 'string' && m.description.trim()) return m.description.trim()
  const skills = Array.isArray(m?.skills) ? m.skills : []
  const text = skills.map((s: any) => (typeof s === 'string' ? s : s?.name || '')).filter(Boolean).join('、')
  return text || 'AI 员工'
}

function insertAt() {
  const base = props.modelValue || ''
  emit('update:modelValue', base && !base.endsWith(' ') ? base + ' @' : base + '@')
}

function pickMention(m: any) {
  const name = String(m.name || m.role_key || '')
  const replaced = (props.modelValue || '').replace(/@([^\s@]*)$/, `@${name} `)
  emit('update:modelValue', replaced)
  mentionQuery.value = null
}

function onEnter(event: KeyboardEvent) {
  if (event.shiftKey) return
  event.preventDefault()
  emit('send')
}

function focus() {
  taRef.value?.focus?.()
}

defineExpose({ focus })
</script>
<style scoped>
.ac-composer {
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--cpq-overlay-w3, rgba(255, 255, 255, 0.04));
}

.ac-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.ac-skill-anchor {
  position: relative;
  flex: none;
}

.ac-plus-btn {
  height: 32px;
  width: 32px;
  border-radius: 50%;
  border: 1px solid var(--cpq-overlay-w8, rgba(255, 255, 255, 0.12));
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  color: var(--cpq-text-primary, #f5f7fa);
  font-size: 18px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
}
.ac-plus-btn:hover {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
.ac-plus-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ac-skill-pop {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  min-width: 220px;
  max-width: 320px;
  max-height: 260px;
  overflow: auto;
  border-radius: 10px;
  border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  background: var(--cpq-bg-elevated, #ffffff);
  box-shadow: 0 8px 24px var(--cpq-shadow-color-strong, rgba(22, 119, 255, 0.14));
  z-index: 30;
  padding: 4px;
}
.ac-skill-head {
  font-size: 11px;
  color: var(--cpq-text-muted, #9aa4b2);
  padding: 6px 8px 2px;
}
.ac-skill-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.ac-skill-item:hover {
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
}
.ac-skill-name {
  font-size: 13px;
  color: var(--cpq-text-primary, #f5f7fa);
}
.ac-skill-desc {
  font-size: 12px;
  color: var(--cpq-text-muted, #9aa4b2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.ac-skill-empty {
  font-size: 12px;
  color: var(--cpq-text-muted, #9aa4b2);
  padding: 8px;
}

.ac-input-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
}

.ac-actions {
  display: flex;
  gap: 6px;
  align-items: flex-end;
}

.ac-at-btn {
  height: 32px;
  min-width: 32px;
  border-radius: 8px;
  border: 1px solid var(--cpq-overlay-w8, rgba(255, 255, 255, 0.12));
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  color: var(--cpq-text-primary, #f5f7fa);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.ac-at-btn:hover {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
.ac-at-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ac-mention-pop {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  right: 0;
  max-height: 220px;
  overflow: auto;
  border-radius: 10px;
  border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  background: var(--cpq-bg-elevated, #ffffff);
  box-shadow: 0 8px 24px var(--cpq-shadow-color-strong, rgba(22, 119, 255, 0.14));
  z-index: 30;
  padding: 4px;
}
.ac-mention-head {
  font-size: 11px;
  color: var(--cpq-text-muted, #9aa4b2);
  padding: 6px 8px 2px;
}
.ac-mention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.ac-mention-item:hover {
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
}
.ac-mention-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  flex: none;
}
.ac-mention-name {
  font-size: 13px;
  color: var(--cpq-text-primary, #f5f7fa);
  flex: none;
}
.ac-mention-desc {
  font-size: 12px;
  color: var(--cpq-text-muted, #9aa4b2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ac-mention-enter-active,
.ac-mention-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.ac-mention-enter-from,
.ac-mention-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* 上下文水位：细进度条 + xx%（绿→黄→红） */
.ac-ctx {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 2px;
}
.ac-ctx-track {
  flex: 1;
  height: 4px;
  border-radius: 999px;
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  overflow: hidden;
}
.ac-ctx-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: #52c41a;
  transition: width 0.2s ease;
}
.ac-ctx-num {
  font-size: 11px;
  color: var(--cpq-text-muted, #9aa4b2);
  white-space: nowrap;
}
.ac-ctx--warn .ac-ctx-fill { background: #faad14; }
.ac-ctx--warn .ac-ctx-num { color: #faad14; }
.ac-ctx--high .ac-ctx-fill { background: #ff4d4f; }
.ac-ctx--high .ac-ctx-num { color: #ff4d4f; }

.ac-composer :deep(.ant-input) {
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  border-color: var(--cpq-overlay-w8, rgba(255, 255, 255, 0.12));
  color: var(--cpq-text-primary, #f5f7fa);
}

.ac-composer :deep(.ant-input::placeholder) {
  color: var(--cpq-text-muted, #9aa4b2);
}
</style>
