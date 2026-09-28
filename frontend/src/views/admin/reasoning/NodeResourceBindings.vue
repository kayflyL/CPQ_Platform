<script setup lang="ts">
/**
 * 节点抽屉「工具层」：机制锁卡 + 已挂载卡 + 尾卡「＋ 添加工具」开弹窗选择器（未挂载工具卡点击即挂）。
 * 卡片与 AI 工具目录同一张脸（ToolCard）——抽屉里看到哪张卡就是目录里哪个工具。
 * 契约不变：v-model:tools = enabled_tools（不含机制锁工具，锁由后端保底补回）。
 */
import { computed, ref } from 'vue'
import ToolCard from '@/components/tools/ToolCard.vue'

const props = withDefaults(defineProps<{
  tools?: string[]
  toolOptions?: Array<{ value: string; label?: string; desc?: string; detail?: string; category?: string; default_enabled?: boolean; display_name?: string; one_liner?: string; custom?: string[] }>
  toolsEnabled?: boolean
  toolsReadonly?: boolean
  /** 机制工具：节点机制必需，锁定勾选不可取消（后端也会保底补回） */
  lockedTools?: string[]
  /** 锁因文案：这些动词为什么不可摘（承载哪条协议），取自 capability_spec.mechanism_reason */
  lockReason?: string
}>(), {
  tools: () => [],
  toolOptions: () => [],
  toolsEnabled: true,
  toolsReadonly: false,
  lockedTools: () => [],
  lockReason: '',
})

const emit = defineEmits<{
  'update:tools': [string[]]
}>()

const poolOpen = ref(false)

const lockedSet = computed(() => new Set((props.lockedTools || []).map(String)))
const optionBy = (name: string) => props.toolOptions.find((o) => String(o.value) === name)
const toTool = (name: string) => {
  const o = optionBy(name) || ({} as any)
  return {
    name,
    category: o.category,
    display_name: o.display_name,
    one_liner: o.one_liner,
    summary: o.desc || '',
    description: o.detail || o.desc || '',
    parameters: (o as any).parameters,
    default_enabled: o.default_enabled,
    custom: o.custom,
  }
}

const lockedCards = computed(() => (props.lockedTools || []).map(toTool))
/** 已挂载增强工具（勾选集 − 机制锁） */
const selectedNames = computed(() =>
  (props.tools || []).filter((t) => !lockedSet.value.has(String(t))))
const selectedCards = computed(() => selectedNames.value.map(toTool))
/** 待选池 = 目录 − 机制锁 − 已挂载 */
const poolCards = computed(() =>
  props.toolOptions
    .filter((o) => !lockedSet.value.has(String(o.value)) && !selectedNames.value.includes(String(o.value)))
    .map((o) => toTool(String(o.value))))

function toggle(name: string) {
  if (lockedSet.value.has(name) || props.toolsReadonly) return
  const next = selectedNames.value.includes(name)
    ? selectedNames.value.filter((t) => t !== name)
    : [...selectedNames.value, name]
  emit('update:tools', next)
}
</script>

<template>
  <div class="node-resource-bindings">
    <section v-if="toolsEnabled" class="nrb-section nrb-card">
      <div class="nrb-section-title">可用工具</div>

      <div v-if="lockedTools.length" class="nrb-locked-block">
        <span class="nrb-field-label">机制必需（节点机制依赖，不可取消）</span>
      </div>

      <div class="nrb-grid">
        <ToolCard
          v-for="t in lockedCards"
          :key="`lk-${t.name}`"
          :tool="t"
          state="locked"
          :lock-note="lockReason"
          compact
        />
        <template v-if="!toolsReadonly">
          <ToolCard
            v-for="t in selectedCards"
            :key="`on-${t.name}`"
            :tool="t"
            state="selected"
            compact
            interactive
            @toggle="toggle"
          />
          <button
            v-if="poolCards.length"
            type="button"
            class="nrb-add-card"
            @click="poolOpen = true"
          >
            ＋ 添加工具
          </button>
        </template>
        <template v-else>
          <ToolCard
            v-for="t in selectedCards"
            :key="`ro-${t.name}`"
            :tool="t"
            state="selected"
            compact
          />
        </template>
      </div>

      <p v-if="lockReason" class="nrb-hint">🔒 {{ lockReason }}</p>
      <p v-if="toolsReadonly" class="nrb-hint">工具由节点类型固定，避免误选导致链路失效。</p>

      <a-modal :open="poolOpen" title="添加工具" width="min(880px, calc(100vw - 32px))" :footer="null"
               wrap-class-name="portal-modal" @cancel="poolOpen = false">
        <p class="nrb-pool-sub">未挂载的工具（点击挂载到本节点，可连续选）；工具目录在 AI 工具目录页维护。</p>
        <div v-if="poolCards.length" class="nrb-grid nrb-grid--pool">
          <ToolCard
            v-for="t in poolCards"
            :key="`pool-${t.name}`"
            :tool="t"
            state="idle"
            compact
            interactive
            @toggle="toggle"
          />
        </div>
        <div v-else class="nrb-pool-empty">没有可挂载的工具——全部已挂载或被机制锁占用。</div>
        <div class="nrb-modal-foot">
          <a-button @click="poolOpen = false">完成</a-button>
        </div>
      </a-modal>
    </section>
  </div>
</template>

<style scoped>
.node-resource-bindings { display: flex; flex-direction: column; gap: 18px; }
.nrb-section { display: flex; flex-direction: column; gap: 12px; }
.nrb-card {
  padding: 14px 15px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 12px;
  background: var(--cpq-glass-2-bg);
  box-shadow: var(--cpq-shadow-sm);
}
.nrb-section-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.nrb-locked-block { display: flex; flex-direction: column; gap: 4px; }
.nrb-field-label { font-size: 12px; color: var(--cpq-text-secondary); }
.nrb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}
.nrb-grid--pool { padding-top: 0; }
.nrb-pool-sub { margin: 0 0 12px; font-size: 12px; color: var(--cpq-text-secondary); }
.nrb-pool-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 12px 0; }
.nrb-modal-foot { display: flex; justify-content: flex-end; margin-top: 8px; }
.nrb-hint { margin: 0; font-size: 12px; line-height: 1.6; color: var(--cpq-text-muted); }
.nrb-add-card {
  display: flex; align-items: center; justify-content: center;
  min-height: 58px;
  padding: 9px 11px;
  border: 1px dashed var(--cpq-border-primary);
  border-radius: 10px;
  background: transparent;
  color: var(--cpq-text-secondary);
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}
.nrb-add-card:hover { border-color: var(--cpq-accent-primary, #1677ff); color: var(--cpq-accent-primary, #1677ff); }
</style>
