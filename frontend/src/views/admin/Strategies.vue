<script setup lang="ts">
/** 策略中心管理页 — 三域 tab 容器（Glass Console）。
 *  各域规则编辑由专门子组件承担：
 *    requirement → ReasoningFlowCanvas（BOM 推理流可视化编排）
 *    selection    → CompatibilityRuleEditor（声明式 WHEN→THEN 兼容性规则）
 *    pricing      → PricingStrategyCanvas（场景化连线画布 + 毛利三档）
 *  原 type 驱动的通用编辑 modal 已随各域专用编辑器落地而移除（确认无打开入口）。 */
import { ref } from 'vue'
import type { StrategyDomain } from '@/api/strategies'
import ReasoningFlowCanvas from './reasoning/ReasoningFlowCanvas.vue'
import CompatibilityRuleEditor from './CompatibilityRuleEditor.vue'
import PricingStrategyCanvas from './PricingStrategyCanvas.vue'

const DOMAINS: { value: StrategyDomain; label: string; hint: string }[] = [
  { value: 'requirement', label: '需求分析', hint: 'BOM 推理流可视化编排（vue flow）· 拖拽/连线/条件分支' },
  { value: 'selection', label: '选型配置', hint: '配件互斥与依赖硬规则，工作台选配时实时校验' },
  { value: 'pricing', label: '报价策略', hint: '报价场景 + 毛利三档规则，可视化连线' },
]
const activeDomain = ref<StrategyDomain>(DOMAINS[0].value)
</script>

<template>
  <div class="page">
    <a-tabs v-model:activeKey="activeDomain" class="strat-tabs">
      <a-tab-pane v-for="d in DOMAINS" :key="d.value">
        <template #tab><span class="tab-label">{{ d.label }}</span></template>
      </a-tab-pane>
    </a-tabs>

    <ReasoningFlowCanvas v-if="activeDomain === 'requirement'" />
    <CompatibilityRuleEditor v-else-if="activeDomain === 'selection'" />
    <PricingStrategyCanvas v-else-if="activeDomain === 'pricing'" />
  </div>
</template>

<style scoped>
.page { padding: 20px 24px; }
.strat-tabs { margin-bottom: 16px; }
.tab-label { margin-right: 6px; }
</style>
