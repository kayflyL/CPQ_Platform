<template>
  <div
    class="ac-composer"
    :class="{ 'ac-dragover': dragOver }"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="dragOver = false"
    @drop.prevent="onDrop"
  >
    <!-- 附件 chip 行：选中即传；状态在卡上（uploading/done/error），✕ 移除（仅未发送） -->
    <div v-if="attachments.length" class="ac-attach-row">
      <div
        v-for="a in attachments"
        :key="a.attachment_id || a.localKey"
        class="ac-attach-chip"
        :class="'is-' + (a.status || 'done')"
        :title="a.error || a.name"
      >
        <span class="ac-attach-icon">{{ attachIcon(a.name) }}</span>
        <span class="ac-attach-name">{{ a.name }}</span>
        <span class="ac-attach-size">{{ sizeText(a.size) }}</span>
        <button
          v-if="a.status !== 'uploading'"
          type="button"
          class="ac-attach-x"
          title="移除"
          @click="$emit('remove-attachment', String(a.attachment_id || a.localKey))"
        >
          ✕
        </button>
      </div>
    </div>
    <div class="ac-row">
      <!-- 工作流入口：私聊=当前角色绑定工作流；群聊=全员工作流并集。点击直接发起（显式 ACTIVE） -->
      <span v-if="showSkills && skillOptions.length" class="ac-skill-anchor">
        <button
          type="button"
          class="ac-plus-btn"
          title="发起工作流"
          :disabled="disabled"
          @click="skillOpen = !skillOpen"
        >
          +
        </button>
        <transition name="ac-mention">
          <div v-if="skillOpen" class="ac-skill-pop" @mousedown.prevent @click.stop>
            <div class="ac-skill-head">工作流</div>
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
            <div v-if="!skillOptions.length" class="ac-skill-empty">暂无可用工作流</div>
          </div>
        </transition>
      </span>
      <div class="ac-input-wrap" @paste="onPaste">
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
        <!-- 附件入口：点选/拖拽/粘贴 → 宿主上传到会话暂存；chip 状态由宿主下发 -->
        <button
          v-if="allowAttach"
          type="button"
          class="ac-attach-btn"
          title="添加附件"
          :disabled="disabled"
          @click="fileInputRef?.click()"
        >
          📎
        </button>
        <input
          v-if="allowAttach"
          ref="fileInputRef"
          type="file"
          multiple
          class="ac-file-input"
          @change="onPickFiles"
        />
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
          class="ac-send"
          :disabled="disabled || (!busy && !modelValue.trim())"
          @click="busy ? $emit('stop') : $emit('send')"
        >
          {{ busy ? '停止' : buttonText }}
        </a-button>
        <!-- 门户等宿主可在发送旁加扩展动作（如「展开」）；不传则不渲染 -->
        <slot name="actions" />
      </div>
    </div>
    <!-- 排队可见化：回合执行中再发的消息被串行扣住，这里给出可数凭据（queue_state 事件驱动） -->
    <div v-if="queued > 0" class="ac-queue">
      <span class="ac-queue-dot"></span>
      <span>已排队 {{ queued }} 条，当前任务完成后自动处理</span>
    </div>
    <!-- 底部元信息行：水位条居左弹性伸展、操作暗示居右；有谁显谁，不各占一层 -->
    <div v-if="hint || contextUsage" class="ac-meta">
      <div v-if="contextUsage" class="ac-ctx" :class="'ac-ctx--' + ctxLevel">
        <div class="ac-ctx-track"><i class="ac-ctx-fill" :style="{ width: ctxPct + '%' }"></i></div>
        <span class="ac-ctx-num">上下文 {{ ctxPct }}%</span>
      </div>
      <div v-if="hint" class="ac-hint">{{ hint }}</div>
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
  /** 排队中消息数（>0 时显示排队徽标）：宿主把 queue_state 事件的深度传进来 */
  queued?: number
  /** 底部提示语（群聊/房间传「@ = 指定该同事接话 · Enter 发送 · 悬停消息可引用」这类操作暗示） */
  hint?: string
  /** 上下文水位（{ ratio }），传入则显示水位条 */
  contextUsage?: { ratio?: number } | null
  /** 附件入口：传入后显示 📎/拖拽/粘贴（仅方案助手聊天面板开启） */
  allowAttach?: boolean
  /** 附件 chip（宿主持有上传状态并下发）；attachment_id=已上传，localKey=上传中 */
  attachments?: Array<{
    attachment_id?: string
    localKey?: string
    name: string
    size: number
    status?: 'uploading' | 'done' | 'error'
    error?: string
  }>
}>(), {
  placeholder: '输入消息…',
  disabled: false,
  sending: false,
  running: false,
  buttonText: '发送',
  members: () => [],
  skills: () => [],
  showSkills: false,
  queued: 0,
  hint: '',
  contextUsage: null,
  allowAttach: false,
  attachments: () => [],
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'pickSkill', skill: any): void
  (e: 'files-picked', files: File[]): void
  (e: 'remove-attachment', key: string): void
}>()

const busy = computed(() => props.sending || props.running)
const taRef = ref<{ focus?: (option?: any) => void } | null>(null)

// ── 附件：点选/拖拽/粘贴 → 交宿主上传（状态由宿主下发到 attachments prop）──
const fileInputRef = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)

function onDragOver() {
  if (!props.allowAttach || props.disabled) return
  dragOver.value = true
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (!props.allowAttach || props.disabled) return
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) emit('files-picked', files)
}

function onPickFiles(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (files.length) emit('files-picked', files)
}

function onPaste(e: ClipboardEvent) {
  if (!props.allowAttach || props.disabled) return
  const files = Array.from(e.clipboardData?.files || [])
  if (files.length) {
    e.preventDefault()
    emit('files-picked', files)
  }
}

function attachIcon(name: string): string {
  const ext = (name.split('.').pop() || '').toLowerCase()
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp'].includes(ext)) return '🖼️'
  if (ext === 'pdf') return 'PDF'
  if (['xlsx', 'xls', 'csv'].includes(ext)) return 'XLS'
  if (['docx', 'doc'].includes(ext)) return 'DOC'
  if (ext === 'zip') return 'ZIP'
  return 'TXT'
}

function sizeText(size: number): string {
  if (!size) return ''
  if (size >= 1024 * 1024) return (size / 1024 / 1024).toFixed(1) + ' MB'
  if (size >= 1024) return Math.round(size / 1024) + ' KB'
  return size + ' B'
}

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
    out.push({ key, name: String(s?.name || key), description: String(s?.description || ''), launchForm: (s as any).launchForm || null })
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
  return text || 'AI 同事'
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
  border-radius: var(--cpq-radius-md);
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
  border-radius: var(--cpq-radius-sm);
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
  border-radius: var(--cpq-radius-sm);
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

/* 发送钮：可用态=品牌色主按钮；空文本/占用中压成玻璃中性灰——「不可点」而非「坏了」 */
.ac-send.ant-btn-primary:disabled {
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  border-color: transparent;
  color: var(--cpq-text-muted, #86909c);
}

.ac-mention-pop {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  right: 0;
  max-height: 220px;
  overflow: auto;
  border-radius: var(--cpq-radius-md);
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
  border-radius: var(--cpq-radius-sm);
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

/* 手机端（≤768）：布局与桌面同构（+ | 输入 | @ | 发送 全单行，IM 惯例形态）；
   仅隐藏 hint——Enter 发送/悬停引用是桌面操作暗示，触屏不成立 */
@media (max-width: 768px) {
  .ac-hint { display: none; }
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

/* 底部元信息行：水位条居左弹性伸展、操作暗示居右，有谁显谁（不再各占一层） */
.ac-meta {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-3);
  padding: 0 2px;
}
.ac-meta .ac-ctx { flex: none; }
.ac-meta .ac-hint { flex: none; max-width: 60%; margin-left: auto; }
.ac-hint {
  font-size: 11px;
  color: var(--cpq-text-muted, #86909c);
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 排队徽标：蓝点呼吸 + 一行说明（queued prop 驱动） */
.ac-queue {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 2px;
  font-size: 11px;
  color: var(--cpq-accent-primary, #1677ff);
}
.ac-queue-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677ff);
  flex: none;
  animation: ac-queue-pulse 1.2s ease-in-out infinite;
}
@keyframes ac-queue-pulse {
  0%, 100% { opacity: 0.35; }
  50% { opacity: 1; }
}

/* 上下文水位：细进度条 + xx%（绿→黄→红） */
.ac-ctx {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2);
}
.ac-ctx-track {
  width: 96px;
  height: 4px;
  border-radius: var(--cpq-radius-full);
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  overflow: hidden;
}
.ac-ctx-fill {
  display: block;
  height: 100%;
  border-radius: var(--cpq-radius-full);
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

/* 拖拽悬停：边框亮起 + 背景微亮（主色，不用渐变；glass token） */
.ac-composer.ac-dragover {
  border-top-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
}

/* 附件 chip 行：位于输入行上方，横向可换行 */
.ac-attach-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--cpq-space-2);
}
.ac-attach-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 240px;
  padding: 4px 8px;
  border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  font-size: 12px;
}
.ac-attach-chip.is-error { border-color: #ff4d4f; }
.ac-attach-chip.is-uploading { opacity: 0.65; }
.ac-attach-icon {
  flex: none;
  font-size: 10px;
  font-weight: 700;
  color: var(--cpq-text-muted, #9aa4b2);
  min-width: 22px;
  text-align: center;
}
.ac-attach-name {
  color: var(--cpq-text-primary, #f5f7fa);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ac-attach-size {
  flex: none;
  color: var(--cpq-text-muted, #9aa4b2);
}
.ac-attach-x {
  flex: none;
  border: none;
  background: transparent;
  color: var(--cpq-text-muted, #9aa4b2);
  cursor: pointer;
  padding: 0 2px;
}
.ac-attach-x:hover { color: var(--cpq-text-primary, #f5f7fa); }

/* 附件按钮：与 @ 按钮同玻璃形态 */
.ac-attach-btn {
  height: 32px;
  min-width: 32px;
  border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-overlay-w8, rgba(255, 255, 255, 0.12));
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  font-size: 14px;
  cursor: pointer;
}
.ac-attach-btn:hover {
  border-color: var(--cpq-accent-primary, #1677ff);
}
.ac-attach-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ac-file-input { display: none; }
</style>
