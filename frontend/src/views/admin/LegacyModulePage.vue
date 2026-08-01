<script setup lang="ts">
/** 需求分析模块页(暂未升级成工作台的模块)—— ModuleScaffold 轻壳 + ReasoningFlowCanvas(编辑器本体零改)。
 *  选型配置已升级成 selection/SelectionWorkspace 工作台(📄 文档库 + 🛠 选型规则 开关,同 PricingWorkspace)。 */
import ModuleScaffold from './ModuleScaffold.vue'
import ReasoningFlowCanvas from './reasoning/ReasoningFlowCanvas.vue'

defineProps<{ module: 'requirement' }>()

const META = {
  requirement: { title: '需求分析', subtitle: 'BOM 推理流可视化编排' },
} as const
</script>

<template>
  <ModuleScaffold :title="META[module].title" :subtitle="META[module].subtitle">
    <ReasoningFlowCanvas />
  </ModuleScaffold>
</template>
