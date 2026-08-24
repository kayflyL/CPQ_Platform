<template>
  <div class="rule-catalog-ref">
    <div class="rcr-head">
      <div class="rcr-title">规则</div>
      <p class="rcr-hint">规则是数据，节点只保存引用类型。执行时按这里选择的规则类型读取 status=active 的规则。</p>
    </div>

    <a-table
      class="rcr-table"
      :data-source="rows"
      :columns="columns"
      :pagination="false"
      size="small"
      row-key="key"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'group'">
          <span class="rcr-group-name">{{ record.label }}</span>
        </template>

        <template v-else-if="column.key === 'types'">
          <div class="rcr-types-cell">
            <a-select
              :value="selectedTypes(record.key)"
              mode="multiple"
              size="small"
              style="width: 100%"
              :placeholder="record.options.length ? '选择小类' : '无可选小类'"
              :options="record.options"
              :max-tag-count="2"
              @change="(values: RuleType[]) => changeGroup(record.key, values)"
            />
            <span v-if="hasDefault(record.key)" class="rcr-default">默认</span>
          </div>
        </template>

        <template v-else-if="column.key === 'rules'">
          <a-popover v-if="selectedTypes(record.key).length" trigger="hover" placement="bottomLeft">
            <template #content>
              <div class="rcr-rule-pop">
                <template v-for="type in selectedTypes(record.key)" :key="type">
                  <div class="rcr-rule-type">{{ RULE_TYPE_META[type]?.label || type }}</div>
                  <div class="rcr-rule-list">
                    <template v-if="rulesByType[type]?.length">
                      <div v-for="rule in rulesByType[type]" :key="rule.id" class="rcr-rule-item">
                        <span class="rcr-rule-dot" />
                        <span>{{ rule.name }}</span>
                      </div>
                    </template>
                    <div v-else class="rcr-empty">暂无启用规则</div>
                  </div>
                </template>
              </div>
            </template>
            <a-button type="link" size="small" class="rcr-rule-trigger">
              查看 {{ activeRuleCount(record.key) }} 条规则
            </a-button>
          </a-popover>
          <span v-else class="rcr-rule-placeholder">未选择小类</span>
        </template>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  requirementRulesApi,
  type RequirementRule,
  type RuleType,
} from '@/api/requirementRules'
import { RULE_GROUPS, RULE_TYPE_META, type RuleGroupKey } from '@/views/admin/selection/requirement-rule-meta'

const props = withDefaults(defineProps<{
  modelValue?: RuleType[]
  available?: RuleType[]
  defaults?: RuleType[]
}>(), {
  modelValue: () => [],
  available: () => RULE_GROUPS.flatMap((group) => group.types),
  defaults: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [RuleType[]]
}>()

const activeRules = ref<RequirementRule[]>([])

onMounted(async () => {
  try {
    const res = await requirementRulesApi.list({ status: 'active' })
    activeRules.value = res.rules || []
  } catch {
    activeRules.value = []
  }
})

const rows = computed(() =>
  RULE_GROUPS
    .map((group) => ({
      key: group.key,
      label: group.label,
      options: group.types
        .filter((type) => props.available.includes(type))
        .map((type) => ({ value: type, label: RULE_TYPE_META[type]?.label || type })),
    }))
    .filter((row) => row.options.length > 0),
)

const rulesByType = computed(() => {
  const map: Partial<Record<RuleType, RequirementRule[]>> = {}
  for (const rule of activeRules.value) {
    if (!rule.type) continue
    if (!map[rule.type]) map[rule.type] = []
    map[rule.type]!.push(rule)
  }
  return map
})

const columns = [
  { title: '大类', dataIndex: 'label', key: 'group', width: 130 },
  { title: '小类', dataIndex: 'options', key: 'types' },
  { title: '规则', dataIndex: 'rules', key: 'rules', width: 180 },
]

function selectedTypes(groupKey: RuleGroupKey): RuleType[] {
  const allowed = rows.value.find((row) => row.key === groupKey)?.options.map((o) => o.value) || []
  return (props.modelValue || []).filter((type) => allowed.includes(type))
}

function changeGroup(groupKey: RuleGroupKey, values: RuleType[]) {
  const group = RULE_GROUPS.find((item) => item.key === groupKey)
  if (!group) return
  const groupSet = new Set(group.types)
  const outside = (props.modelValue || []).filter((type) => !groupSet.has(type))
  emit('update:modelValue', [...outside, ...values])
}

function activeRuleCount(groupKey: RuleGroupKey): number {
  return selectedTypes(groupKey).reduce(
    (count, type) => count + (rulesByType.value[type]?.length || 0),
    0,
  )
}

function hasDefault(groupKey: RuleGroupKey): boolean {
  const group = RULE_GROUPS.find((item) => item.key === groupKey)
  if (!group) return false
  return group.types.some((type) => props.defaults.includes(type))
}
</script>

<style scoped>
.rule-catalog-ref { display: flex; flex-direction: column; gap: 8px; }
.rcr-head { display: flex; flex-direction: column; gap: 4px; }
.rcr-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.rcr-hint { margin: 0; font-size: 12px; line-height: 1.6; color: var(--cpq-text-muted); }
.rcr-group-name { font-weight: 600; }
.rcr-types-cell { display: flex; align-items: center; gap: 8px; }
.rcr-default {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(22, 119, 255, 0.16);
  color: #6ea8ff;
}
.rcr-rule-trigger { padding: 0 4px; height: 24px; font-size: 12px; }
.rcr-rule-placeholder { color: var(--cpq-text-muted); font-size: 12px; }
.rcr-rule-pop { max-width: 320px; max-height: 320px; overflow: auto; }
.rcr-rule-type { margin-bottom: 4px; font-size: 12px; font-weight: 600; }
.rcr-rule-list { margin-bottom: 10px; display: flex; flex-direction: column; gap: 4px; }
.rcr-rule-item { display: flex; align-items: center; gap: 6px; font-size: 12px; line-height: 1.5; }
.rcr-rule-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--cpq-accent-color, #1677ff); flex: 0 0 auto; }
.rcr-empty { color: var(--cpq-text-muted); font-size: 12px; }
</style>
