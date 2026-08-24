<template>
  <div class="rrc">
    <div class="rrc-head">
      <div>
        <div class="rrc-title">需求分析配置中心</div>
        <div class="rrc-hint">需求引导、语义字典和选型策略集中维护；列表只展示业务字段，编辑使用结构化表单。</div>
      </div>
      <a-space>
        <a-button size="small" @click="resetDefaults">重置默认</a-button>
        <a-button type="primary" size="small" @click="startAdd">+ 新建规则</a-button>
      </a-space>
    </div>

    <a-radio-group v-model:value="activeGroup" button-style="solid" size="small">
      <a-radio-button v-for="g in RULE_GROUPS" :key="g.key" :value="g.key">{{ g.label }}</a-radio-button>
    </a-radio-group>

    <div class="rrc-layout">
      <aside class="rrc-side glass-light">
        <div v-for="t in activeGroupMeta.types" :key="t" class="rrc-side-item" :class="{ 'is-active': activeType === t }" @click="activeType = t">
          <span>{{ RULE_TYPE_META[t].label }}</span>
          <span class="rrc-count">{{ typeCounts[t] || 0 }}</span>
        </div>
      </aside>

      <section class="rrc-content">
        <div class="rrc-toolbar">
          <div>
            <div class="rrc-type-title">{{ activeTypeMeta.label }}</div>
            <div class="rrc-type-hint">{{ activeTypeMeta.hint }}</div>
          </div>
          <a-space>
            <a-input-search v-model:value="searchText" placeholder="搜索名称或内容" allow-clear style="width: 220px" />
            <a-select v-model:value="statusFilter" :options="STATUS_FILTER_OPTIONS" allow-clear placeholder="全部状态" style="width: 130px" />
          </a-space>
        </div>

        <a-table
          v-if="activeTypeMeta.layout === 'table'"
          :columns="columns"
          :data-source="visibleRules"
          :loading="loading"
          row-key="id"
          size="small"
          :pagination="{ pageSize: 20, showSizeChanger: false }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <div class="rrc-name">{{ record.name }}</div>
            </template>
            <template v-else-if="column.key === 'summary'">
              <div class="rrc-summary">{{ ruleSummary(record) }}</div>
            </template>
            <template v-else-if="column.key === 'status'">
              <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
            </template>
            <template v-else-if="column.key === 'hit'">
              <a-tooltip :title="record.last_hit_at || '暂无命中时间'">
                <span>{{ record.hit_count || 0 }}</span>
              </a-tooltip>
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-space :size="2">
                <a-button type="text" size="small" @click="startEdit(record)"><EditOutlined /></a-button>
                <a-button type="text" size="small" danger @click="remove(record)"><DeleteOutlined /></a-button>
              </a-space>
            </template>
          </template>
        </a-table>

        <RequirementStrategyPanels
          v-else
          :rules="visibleRules"
          :layout="activeTypeMeta.layout"
          :loading="loading"
          @save="saveSpecial"
          @remove="remove"
        />
      </section>
    </div>

    <RequirementRuleEditDrawer
      v-model:open="editorOpen"
      :editing="editing"
      :default-type="activeType"
      :saving="saving"
      @save="saveRule"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons-vue'
import { requirementRulesApi, type RequirementRule, type RuleStatus, type RuleType } from '@/api/requirementRules'
import {
  RULE_GROUPS,
  RULE_TYPE_META,
  STATUS_OPTIONS,
  ruleSummary,
} from './requirement-rule-meta'
import RequirementRuleEditDrawer from './RequirementRuleEditDrawer.vue'
import RequirementStrategyPanels from './RequirementStrategyPanels.vue'

const rules = ref<RequirementRule[]>([])
const loading = ref(false)
const activeGroup = ref<'understand' | 'dictionary' | 'strategy'>('understand')
const activeType = ref<RuleType>('clarity')
const statusFilter = ref<RuleStatus | undefined>(undefined)
const searchText = ref('')
const editorOpen = ref(false)
const editing = ref<RequirementRule | null>(null)
const saving = ref(false)

const STATUS_FILTER_OPTIONS = STATUS_OPTIONS
const columns = [
  { title: '规则名称', key: 'name', dataIndex: 'name', width: 220 },
  { title: '内容摘要', key: 'summary' },
  { title: '状态', key: 'status', width: 90 },
  { title: '命中', key: 'hit', width: 80 },
  { title: '操作', key: 'actions', width: 90, align: 'center' as const },
]

const activeGroupMeta = computed(() => RULE_GROUPS.find(g => g.key === activeGroup.value) || RULE_GROUPS[0])
const activeTypeMeta = computed(() => RULE_TYPE_META[activeType.value])

const typeCounts = computed<Record<RuleType, number>>(() => {
  const out = {} as Record<RuleType, number>
  for (const r of rules.value) out[r.type] = (out[r.type] || 0) + 1
  return out
})

const visibleRules = computed(() => {
  const q = searchText.value.trim().toLowerCase()
  return rules.value.filter((r) => {
    if (r.type !== activeType.value) return false
    if (statusFilter.value && r.status !== statusFilter.value) return false
    if (!q) return true
    return r.name.toLowerCase().includes(q) || ruleSummary(r).toLowerCase().includes(q)
  })
})

watch(activeGroup, (group) => {
  const meta = RULE_GROUPS.find(g => g.key === group)
  if (meta && !meta.types.includes(activeType.value)) activeType.value = meta.types[0]
})

async function loadAll() {
  loading.value = true
  try {
    const r = await requirementRulesApi.list()
    rules.value = r.rules || []
  } catch (e: any) {
    message.error(e.response?.data?.detail || '规则加载失败')
    rules.value = []
  } finally {
    loading.value = false
  }
}
onMounted(loadAll)

function startAdd() {
  editing.value = null
  editorOpen.value = true
}

function startEdit(rule: RequirementRule) {
  editing.value = rule
  editorOpen.value = true
}

async function saveRule(payload: any) {
  if (payload.error) {
    message.error(payload.error)
    return
  }
  saving.value = true
  try {
    const data = {
      type: payload.type,
      name: payload.name,
      status: payload.status,
      body: payload.body,
      description: payload.description,
      change_reason: payload.change_reason,
    }
    if (payload.id) await requirementRulesApi.update(payload.id, data)
    else await requirementRulesApi.create(data)
    message.success('已保存（下次推理生效）')
    editorOpen.value = false
    await loadAll()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function saveSpecial(payload: { id?: number; name: string; status: string; body: Record<string, any> }) {
  if (!payload.id) return
  try {
    await requirementRulesApi.update(payload.id, {
      name: payload.name,
      status: payload.status as RuleStatus,
      body: payload.body,
    })
    message.success('已保存')
    await loadAll()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}

function remove(rule: RequirementRule) {
  Modal.confirm({
    title: '删除规则？',
    content: rule.name,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await requirementRulesApi.remove(rule.id)
        message.success('已删除')
        await loadAll()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除失败')
      }
    },
  })
}

function resetDefaults() {
  Modal.confirm({
    title: '重置为默认规则？',
    content: '将清空全部规则和样本并恢复默认 seed。',
    okText: '重置',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await requirementRulesApi.reset()
        message.success('已重置')
        await loadAll()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '重置失败')
      }
    },
  })
}

function statusColor(status: string) {
  if (status === 'active') return 'success'
  if (status === 'testing') return 'processing'
  if (status === 'draft') return 'default'
  return 'warning'
}
</script>

<style scoped>
.rrc { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.rrc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.rrc-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary); }
.rrc-hint { font-size: 12px; color: var(--cpq-text-muted); margin: 4px 0 0; }
.rrc-layout { display: grid; grid-template-columns: 210px 1fr; gap: 12px; min-height: 0; }
.rrc-side { display: flex; flex-direction: column; gap: 4px; padding: 10px; border-radius: 12px; border: 1px solid var(--cpq-border-primary); background: var(--cpq-glass-1-bg); }
.rrc-side-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 8px; cursor: pointer; color: var(--cpq-text-secondary); font-size: 13px; }
.rrc-side-item:hover { background: var(--cpq-overlay-w6); }
.rrc-side-item.is-active { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); font-weight: 600; }
.rrc-count { font-size: 11px; color: var(--cpq-text-muted); }
.rrc-content { min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.rrc-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.rrc-type-title { font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); }
.rrc-type-hint { font-size: 12px; color: var(--cpq-text-muted); margin-top: 2px; }
.rrc-name { font-weight: 600; color: var(--cpq-text-primary); }
.rrc-summary { color: var(--cpq-text-secondary); font-size: 12px; line-height: 1.5; word-break: break-all; }
</style>
