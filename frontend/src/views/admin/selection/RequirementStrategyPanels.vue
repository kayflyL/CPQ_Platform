<template>
  <a-spin :spinning="loading">
    <div v-if="!current" class="rrc-empty">暂无规则，请点击右上角新建</div>

    <div v-else-if="layout === 'capacity'" class="rrc-panel glass-light">
      <div class="rrc-panel-head">
        <div>
          <div class="rrc-panel-title">容量匹配策略</div>
          <div class="rrc-panel-hint">未明确接口或容量时使用的匹配默认值</div>
        </div>
        <a-tag :color="statusColor(form.status)">{{ form.status }}</a-tag>
      </div>
      <div class="rrc-grid">
        <a-form-item label="匹配策略"><a-input v-model:value="form.strategy" /></a-form-item>
        <a-form-item label="容差"><a-input-number v-model:value="form.tolerance" :min="0" style="width: 100%" /></a-form-item>
        <a-form-item label="默认接口"><a-input v-model:value="form.default_interface" placeholder="如：SATA" /></a-form-item>
      </div>
      <div class="rrc-panel-actions">
        <a-button size="small" @click="save">保存</a-button>
        <a-button size="small" danger type="text" @click="remove">删除</a-button>
      </div>
    </div>

    <div v-else-if="layout === 'fallback'" class="rrc-panel glass-light">
      <div class="rrc-panel-head">
        <div>
          <div class="rrc-panel-title">机型选型放宽顺序</div>
          <div class="rrc-panel-hint">越靠前优先级越高，拖拽调整顺序</div>
        </div>
        <a-tag :color="statusColor(form.status)">{{ form.status }}</a-tag>
      </div>
      <draggable v-model="form.order" :item-key="orderKey" class="rrc-order-list">
        <template #item="{ element }">
          <div class="rrc-order-item">⠿ {{ element }}</div>
        </template>
      </draggable>
      <a-form-item label="无信号策略"><a-input v-model:value="form.no_signal_strategy" /></a-form-item>
      <div class="rrc-panel-actions">
        <a-button size="small" @click="save">保存</a-button>
        <a-button size="small" danger type="text" @click="remove">删除</a-button>
      </div>
    </div>

    <div v-else-if="layout === 'check'" class="rrc-panel glass-light">
      <div class="rrc-panel-head">
        <div>
          <div class="rrc-panel-title">方案自检</div>
          <div class="rrc-panel-hint">生成方案后执行的检查项</div>
        </div>
        <a-tag :color="statusColor(form.status)">{{ form.status }}</a-tag>
      </div>
      <div class="rrc-check-list">
        <div v-for="c in CHECK_OPTIONS" :key="c.value" class="rrc-check-row">
          <span>{{ c.label }}</span>
          <a-switch v-model:checked="form.checks[c.value]" />
        </div>
      </div>
      <a-form-item label="失败处理"><a-input v-model:value="form.on_fail" /></a-form-item>
      <div class="rrc-panel-actions">
        <a-button size="small" @click="save">保存</a-button>
        <a-button size="small" danger type="text" @click="remove">删除</a-button>
      </div>
    </div>
  </a-spin>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import draggable from 'vuedraggable'
import type { RequirementRule } from '@/api/requirementRules'
import type { RuleLayout } from './requirement-rule-meta'

const props = defineProps<{ rules: RequirementRule[]; layout: RuleLayout; loading: boolean }>()
const emit = defineEmits<{
  (e: 'save', payload: { id?: number; name: string; status: string; body: Record<string, any> }): void
  (e: 'remove', rule: RequirementRule): void
}>()

const CHECK_OPTIONS = [
  { value: 'plan_not_empty', label: '方案不能为空' },
  { value: 'required_fields', label: '必填字段完整' },
  { value: 'qty_reasonable', label: '数量合理' },
]

const current = computed(() => props.rules[0] || null)

function orderKey(item: string) {
  return item
}

const form = reactive<Record<string, any>>({
  name: '',
  status: 'active',
  strategy: 'tolerance',
  tolerance: 10,
  default_interface: '',
  order: ['exact', 'same_series', 'same_form', 'all'],
  no_signal_strategy: 'return_empty',
  checks: { plan_not_empty: true, required_fields: true, qty_reasonable: true },
  on_fail: 'mark',
})

watch(current, (r) => {
  if (!r) return
  const b = r.body || {}
  form.name = r.name
  form.status = r.status
  if (props.layout === 'capacity') {
    form.strategy = b.strategy || 'tolerance'
    form.tolerance = b.tolerance ?? 10
    form.default_interface = b.default_interface || ''
  }
  if (props.layout === 'fallback') {
    form.order = Array.isArray(b.order) ? [...b.order] : ['exact', 'same_series', 'same_form', 'all']
    form.no_signal_strategy = b.no_signal_strategy || 'return_empty'
  }
  if (props.layout === 'check') {
    form.checks = { plan_not_empty: true, required_fields: true, qty_reasonable: true, ...(b.checks || {}) }
    form.on_fail = b.on_fail || 'mark'
  }
}, { immediate: true })

function statusColor(status: string) {
  return status === 'active' ? 'success' : status === 'testing' ? 'processing' : status === 'draft' ? 'default' : 'warning'
}

function buildBody() {
  if (props.layout === 'capacity') return { strategy: form.strategy, tolerance: form.tolerance, default_interface: form.default_interface }
  if (props.layout === 'fallback') return { order: form.order, no_signal_strategy: form.no_signal_strategy }
  return { checks: form.checks, on_fail: form.on_fail }
}

function save() {
  if (!current.value) return
  emit('save', { id: current.value.id, name: form.name || current.value.name, status: form.status, body: buildBody() })
}

function remove() {
  if (current.value) emit('remove', current.value)
}
</script>

<style scoped>
.rrc-empty { color: var(--cpq-text-muted); font-size: 12px; text-align: center; padding: 24px 0; }
.rrc-panel { padding: 14px; border-radius: 12px; border: 1px solid var(--cpq-border-primary); background: var(--cpq-glass-1-bg); }
.rrc-panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.rrc-panel-title { font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); }
.rrc-panel-hint { margin-top: 4px; font-size: 12px; color: var(--cpq-text-muted); }
.rrc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0 12px; }
.rrc-order-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.rrc-order-item { padding: 8px 10px; border: 1px solid var(--cpq-border-primary); border-radius: 8px; background: var(--cpq-glass-1-bg); cursor: move; }
.rrc-check-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.rrc-check-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border: 1px solid var(--cpq-border-primary); border-radius: 8px; background: var(--cpq-glass-1-bg); }
.rrc-panel-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
</style>
