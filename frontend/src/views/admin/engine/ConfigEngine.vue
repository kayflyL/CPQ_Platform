<script setup lang="ts">
/** 配置引擎(设置 · /settings/engine)—— 工作流治理面整体迁自策略中心(2026-11-07):
 *  兼容规则 / BOM案例库 / 需求分析规则 / 报价策略 四个治理面,独立权限 page.engine。
 *  各治理面组件原样复用(引擎判定直读 DB,规则改动下一次 resolve 即生效)。
 */
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ToolOutlined, FileTextOutlined, ScheduleOutlined, DollarOutlined } from '@ant-design/icons-vue'
import CompatibilityRuleEditor from '@/views/admin/CompatibilityRuleEditor.vue'
import BomCaseLibrary from '@/views/admin/selection/BomCaseLibrary.vue'
import RequirementRules from '@/views/admin/requirement/RequirementRules.vue'
import PricingWorkspace from '@/views/admin/pricing/PricingWorkspace.vue'

const route = useRoute()
const router = useRouter()

type Tab = 'selection' | 'cases' | 'requirement' | 'pricing'
const TABS: Array<{ key: Tab; label: string; icon: any }> = [
  { key: 'selection', label: '兼容规则', icon: ToolOutlined },
  { key: 'cases', label: 'BOM 案例库', icon: FileTextOutlined },
  { key: 'requirement', label: '需求分析规则', icon: ScheduleOutlined },
  { key: 'pricing', label: '报价策略', icon: DollarOutlined },
]
const VALID: Tab[] = ['selection', 'cases', 'requirement', 'pricing']

const tab = ref<Tab>(VALID.includes(route.query.tab as Tab) ? (route.query.tab as Tab) : 'selection')
watch(tab, (v) => { router.replace({ query: { ...route.query, tab: v } }) })
watch(() => route.query.tab, (v) => {
  if (VALID.includes(v as Tab) && v !== tab.value) tab.value = v as Tab
})
</script>

<template>
  <div class="ce">
    <div class="ce-bar glass-light">
      <span class="ce-title">配置引擎</span>
      <span class="ce-sub">选配规则 / 案例库 / 需求规则 / 定价策略 —— 改完即时生效,人工选配与 AI 工作流共用同一判定</span>
      <a-radio-group v-model:value="tab" button-style="solid" size="small" class="ce-tabs">
        <a-radio-button v-for="t in TABS" :key="t.key" :value="t.key">
          <component :is="t.icon" /> {{ t.label }}
        </a-radio-button>
      </a-radio-group>
    </div>
    <div class="ce-body">
      <CompatibilityRuleEditor v-if="tab === 'selection'" />
      <BomCaseLibrary v-else-if="tab === 'cases'" />
      <RequirementRules v-else-if="tab === 'requirement'" />
      <PricingWorkspace v-else-if="tab === 'pricing'" />
    </div>
  </div>
</template>

<style scoped>
.ce { display: flex; flex-direction: column; padding: 8px 24px 40px; }
.ce-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 20px; border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-glass-border); margin-bottom: 16px;
  position: sticky; top: calc(var(--cpq-sticky-top, 0px) + 12px); z-index: 5;
}
.ce-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary); white-space: nowrap; }
.ce-sub { flex: 1; min-width: 0; font-size: 12px; color: var(--cpq-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ce-tabs { flex-shrink: 0; }
.ce-tabs :deep(.ant-radio-button-wrapper) { display: inline-flex; align-items: center; gap: 4px; }
.ce-body { flex: 1; min-height: 0; }

@media (max-width: 768px) {
  .ce { padding: 8px 12px 40px; }
  .ce-bar { position: static; flex-wrap: wrap; gap: 8px 12px; padding: 9px 12px; }
  .ce-sub { display: none; }
  .ce-tabs { width: 100%; overflow-x: auto; }
  .ce-tabs :deep(.ant-radio-group) { display: inline-flex; white-space: nowrap; }
  .ce-tabs :deep(.ant-radio-button-wrapper) { flex-shrink: 0; }
}
</style>
