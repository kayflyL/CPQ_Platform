<script setup lang="ts">
/**
 * 规则卡（规则层统一卡片语法，与 ToolCard 同脸）：
 * kind=group（整组引入，组内新增自动跟进）/ rule（单条）；
 * idle=待选（卡底「＋ 加入」）、selected=已引入（卡底「移除」）；非 active 状态右上灰标签（草稿/测试中/已停用）。
 * 可选扩展：badge=徽标文案（默认「组/条」）、tone=徽标配色（默认随 kind）、#actions=卡底左侧插槽（需求规则页放编辑/删除）。
 * 规则本体的编辑在策略中心·需求分析规则页，抽屉里的此卡只做引入/移除。
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  kind: 'group' | 'rule'
  name: string
  /** 组卡=「整组 N 条 · 新增自动跟进」；条卡=所属组名 */
  meta?: string
  /** 组卡=用法行 */
  summary?: string
  status?: string
  state?: 'idle' | 'selected'
  interactive?: boolean
  /** 徽标文案，默认按 kind 显示「组/条」 */
  badge?: string
  /** 徽标配色：group=蓝底、rule=中性灰，默认随 kind */
  tone?: 'group' | 'rule'
}>(), {
  meta: '',
  summary: '',
  status: 'active',
  state: 'idle',
  interactive: false,
  badge: '',
})

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'remove'): void
}>()

const archived = computed(() => props.status !== 'active')
const STATUS_LABELS: Record<string, string> = { draft: '草稿', testing: '测试中', archived: '已停用' }
const statusLabel = computed(() => (props.status === 'active' ? '' : (STATUS_LABELS[props.status] || '已停用')))
const badgeText = computed(() => props.badge || (props.kind === 'group' ? '组' : '条'))
const toneCls = computed(() => (props.tone || props.kind) === 'group' ? 'rc-mono--group' : 'rc-mono--rule')

function onAct() {
  if (!props.interactive) return
  if (archived.value && props.state === 'idle') return
  if (props.state === 'selected') emit('remove')
  else emit('add')
}
</script>

<template>
  <div class="rule-card" :class="[`is-${state}`, { 'is-archived': archived }]">
    <div class="rc-top">
      <span class="rc-mono" :class="toneCls">{{ badgeText }}</span>
      <span v-if="statusLabel" class="rc-state">{{ statusLabel }}</span>
    </div>
    <div class="rc-title" :title="name">{{ name }}</div>
    <div v-if="meta" class="rc-meta">{{ meta }}</div>
    <div v-if="summary" class="rc-summary">{{ summary }}</div>
    <div v-if="interactive || $slots.actions" class="rc-foot">
      <span class="rc-side">
        <slot name="actions">
          <span v-if="state === 'selected'" class="rc-mounted">已引入</span>
        </slot>
      </span>
      <button
        v-if="interactive"
        type="button"
        class="rc-act"
        :class="state === 'selected' ? 'rc-act--remove' : 'rc-act--mount'"
        :disabled="archived && state !== 'selected'"
        @click.stop="onAct"
      >{{ state === 'selected' ? '移除' : '＋ 加入' }}</button>
    </div>
  </div>
</template>

<style scoped>
.rule-card {
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-2);
  padding: var(--cpq-space-3);
  min-width: 0;
  border: 1px solid var(--cpq-border-primary);
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-glass-1-bg);
  box-shadow: var(--cpq-shadow-sm);
  transition: transform var(--cpq-dur-1) var(--cpq-ease-smooth), box-shadow var(--cpq-dur-1) var(--cpq-ease-smooth), border-color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.rule-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--cpq-shadow-md);
}
.rule-card.is-selected {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-glass-2-bg);
}
.rule-card.is-archived { opacity: .55; }

.rc-top { display: flex; align-items: center; justify-content: space-between; gap: var(--cpq-space-2); }
.rc-mono {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; flex-shrink: 0;
  border-radius: var(--cpq-radius-sm);
  font-size: var(--cpq-font-size-base); font-weight: 600;
}
.rc-mono--group {
  background: var(--cpq-overlay-a15);
  color: color-mix(in srgb, var(--cpq-accent-primary) 78%, var(--cpq-text-primary));
}
.rc-mono--rule {
  background: var(--cpq-glass-2-bg); color: var(--cpq-text-secondary);
  border: 1px solid var(--cpq-border-primary);
}
.rc-state { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.rc-title {
  font-size: var(--cpq-font-size-base); font-weight: 600; color: var(--cpq-text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rc-meta {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted);
}
.rc-summary {
  flex: 1;
  font-size: var(--cpq-font-size-sm); line-height: 1.55; color: var(--cpq-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.rc-foot {
  display: flex; align-items: center; justify-content: space-between; min-height: 24px;
}
.rc-side { display: inline-flex; align-items: center; gap: var(--cpq-space-1); min-width: 0; }
.rc-mounted { font-size: var(--cpq-font-size-xs); color: var(--cpq-accent-primary); }
.rc-act {
  padding: 1px 10px;
  border-radius: var(--cpq-radius-full);
  border: 1px solid var(--cpq-border-primary);
  background: transparent;
  font-size: var(--cpq-font-size-xs);
  line-height: 1.7;
  color: var(--cpq-text-secondary);
  cursor: pointer;
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth), color var(--cpq-dur-1) var(--cpq-ease-smooth), background var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.rc-act--mount {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
}
.rc-act--mount:hover { background: var(--cpq-overlay-a10); }
.rc-act--remove:hover { border-color: var(--cpq-accent-danger); color: var(--cpq-accent-danger); }
.rc-act:disabled { cursor: not-allowed; opacity: .6; }
</style>
