<script setup lang="ts">
/** 推理流节点（X6 Vue 节点，注册名 reasoning-node）。
 *  玻璃卡显示：步骤 key + 名称 + 一句话说明 + 用到的策略/数据源标注 + 可配置指示。
 *  data 由 ReasoningFlowCanvas 注入（x6-vue-shape 传 props.data）。 */
import { computed } from 'vue'

const NODE_META: Record<string, { desc: string; sources: string[] }> = {
  extract: { desc: 'jieba 分词 + 词表命中，提取关键词/品类/系列/形态', sources: ['词表', 'jieba'] },
  select_baseline: { desc: '按系列/形态四级兜底选机型骨架', sources: ['model_recommend', 'base_configs'] },
  match_kp: { desc: '型号 token 精确命中优先，否则按品类别名挑代表件', sources: ['别名表', 'kp 库'] },
  compose: { desc: '每 baseline × 同组 KP 组合整机方案', sources: ['build_plan'] },
  review: { desc: '方案就绪，下发整机方案清单', sources: [] },
}

const props = defineProps<{ data: any }>()
const meta = computed(() => NODE_META[props.data?.key] || { desc: '', sources: [] })
</script>

<template>
  <div class="rf-node glass-light" :class="{ 'rf-node--cfg': data?.configurable }">
    <div class="rf-node-head">
      <span class="rf-node-key">{{ data?.key }}</span>
      <span v-if="data?.configurable" class="rf-node-cfg">可配置</span>
    </div>
    <div class="rf-node-label">{{ data?.label }}</div>
    <div class="rf-node-desc">{{ meta.desc }}</div>
    <div v-if="meta.sources.length" class="rf-node-sources">
      <span v-for="s in meta.sources" :key="s" class="rf-source">{{ s }}</span>
    </div>
  </div>
</template>

<style scoped>
.rf-node {
  width: 220px; padding: 10px 12px;
  border-radius: var(--cpq-radius-md, 12px);
  cursor: pointer;
}
.rf-node--cfg { border-color: var(--cpq-glass-border-strong) !important; }
.rf-node-head { display: flex; align-items: center; justify-content: space-between; }
.rf-node-key {
  font-size: 11px; font-family: ui-monospace, monospace;
  color: var(--cpq-text-muted); text-transform: lowercase; letter-spacing: .5px;
}
.rf-node-cfg {
  font-size: 10px; padding: 0 6px; border-radius: 6px;
  background: var(--cpq-overlay-w10); color: var(--cpq-accent-primary);
}
.rf-node-label { font-weight: 600; color: var(--cpq-text-primary); margin-top: 4px; font-size: 14px; }
.rf-node-desc { font-size: 12px; color: var(--cpq-text-secondary); margin-top: 4px; line-height: 1.45; }
.rf-node-sources { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.rf-source {
  font-size: 10px; padding: 1px 6px; border-radius: 6px;
  background: var(--cpq-overlay-w8); color: var(--cpq-accent-primary);
}
</style>
