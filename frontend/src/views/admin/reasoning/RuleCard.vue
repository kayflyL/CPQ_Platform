<script setup lang="ts">
/**
 * 规则卡（节点抽屉·规则层统一卡片语法，与 ToolCard 同脸）：
 * kind=group（整组引入，组内新增自动跟进）/ rule（单条）；
 * idle=待选（卡底「＋ 加入」）、selected=已引入（卡底「移除」）；archived 灰显不可加入。
 * 规则本体的编辑在策略中心·需求分析规则页，此卡只做引入/移除。
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
}>(), {
  meta: '',
  summary: '',
  status: 'active',
  state: 'idle',
  interactive: false,
})

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'remove'): void
}>()

const archived = computed(() => props.status !== 'active')

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
      <span class="rc-mono" :class="kind === 'group' ? 'rc-mono--group' : 'rc-mono--rule'">
        {{ kind === 'group' ? '组' : '条' }}
      </span>
      <span v-if="archived" class="rc-state">已停用</span>
    </div>
    <div class="rc-title" :title="name">{{ name }}</div>
    <div v-if="meta" class="rc-meta">{{ meta }}</div>
    <div v-if="summary" class="rc-summary">{{ summary }}</div>
    <div class="rc-foot">
      <template v-if="interactive">
        <span v-if="state === 'selected'" class="rc-mounted">已引入</span>
        <button
          type="button"
          class="rc-act"
          :class="state === 'selected' ? 'rc-act--remove' : 'rc-act--mount'"
          :disabled="archived && state !== 'selected'"
          @click.stop="onAct"
        >{{ state === 'selected' ? '移除' : '＋ 加入' }}</button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.rule-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 11px 12px 10px;
  min-width: 0;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 12px;
  background: var(--cpq-glass-1-bg);
  box-shadow: var(--cpq-shadow-sm);
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.rule-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--cpq-shadow-md, 0 4px 12px rgba(0, 0, 0, 0.12));
}
.rule-card.is-selected {
  border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-glass-2-bg);
}
.rule-card.is-archived { opacity: .55; }

.rc-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rc-mono {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; flex-shrink: 0;
  border-radius: 9px;
  font-size: 13px; font-weight: 700;
}
.rc-mono--group { background: rgba(22, 119, 255, 0.16); color: #6ea8ff; }
.rc-mono--rule {
  background: var(--cpq-glass-2-bg); color: var(--cpq-text-secondary);
  border: 1px solid var(--cpq-border-primary);
}
.rc-state { font-size: 11px; color: var(--cpq-text-muted); }
.rc-title {
  font-size: 13px; font-weight: 700; color: var(--cpq-text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rc-meta { font-size: 11px; color: var(--cpq-text-muted); }
.rc-summary {
  flex: 1;
  font-size: 12px; line-height: 1.55; color: var(--cpq-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.rc-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  min-height: 24px;
}
.rc-mounted { font-size: 11.5px; color: var(--cpq-accent-primary, #6ea8ff); }
.rc-act {
  padding: 1px 10px;
  border-radius: 999px;
  border: 1px solid var(--cpq-border-primary);
  background: transparent;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--cpq-text-secondary);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.rc-act--mount {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
.rc-act--mount:hover { background: rgba(22, 119, 255, 0.10); }
.rc-act--remove:hover { border-color: #ff7875; color: #ff7875; }
.rc-act:disabled { cursor: not-allowed; opacity: .6; }
</style>
