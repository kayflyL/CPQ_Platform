<script setup lang="ts">
/** vue flow 自定义节点（注册名 rf）。复用 Glass Console 玻璃卡样式 + 左右 Handle。
 *  data 由 ReasoningFlowCanvas 注入：{ stepType, label, configurable }。
 *  P2.2 加 condition（多出口 Handle）/ llm 时在此扩 meta + 分支渲染。 */
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const NODE_META: Record<string, { desc: string; sources: string[] }> = {
  extract: { desc: 'jieba 分词 + 词表命中，提取关键词/品类/系列/形态', sources: ['词表', 'jieba'] },
  select_baseline: { desc: '按系列/形态四级兜底选机型骨架', sources: ['model_recommend', 'base_configs'] },
  match_kp: { desc: '型号 token 精确命中优先，否则按品类别名挑代表件', sources: ['别名表', 'kp 库'] },
  compose: { desc: '每 baseline × 同组 KP 组合整机方案', sources: ['build_plan'] },
  review: { desc: '方案就绪，下发整机方案清单', sources: [] },
  condition: { desc: '条件判断：按表达式求值选分支', sources: ['expr'] },
  clarity_check: { desc: '读规则库评估明确度，不明确触发反问', sources: ['clarity 规则'] },
  ask_user: { desc: '按缺失字段挑话术，暂停 pipeline 等回复', sources: ['rebuttal 话术'] },
  budget_check: { desc: '给方案注超预算标注（不剔除）', sources: ['预算规则'] },
  llm: { desc: 'LLM 节点（P2.2 预留）', sources: [] },
}
const props = defineProps<{ id: string; data: any }>()
const stepType = computed(() => props.data?.stepType || '')
const meta = computed(() => NODE_META[stepType.value] || { desc: '', sources: [] })
</script>

<template>
  <div class="rf-node-vf glass-light" :class="{
    'rf-node--cfg': data?.configurable,
    'rf-node--running': data?.execState === 'running',
    'rf-node--done': data?.execState === 'done',
    'rf-node--trace': data?.trace,
    'rf-node--dim': data?.dim,
  }">
    <Handle type="target" :position="Position.Left" class="rf-handle" />
    <div class="rf-head">
      <span class="rf-key">{{ stepType }}</span>
      <div class="rf-head-tags">
        <span v-if="data?.badge" class="rf-badge">{{ data.badge }}</span>
        <span v-if="data?.configurable" class="rf-cfg-tag">可配置</span>
      </div>
    </div>
    <div class="rf-label">{{ data?.label }}</div>
    <div class="rf-desc">{{ meta.desc }}</div>
    <div v-if="meta.sources.length" class="rf-sources">
      <span v-for="s in meta.sources" :key="s" class="rf-source">{{ s }}</span>
    </div>
    <Handle type="source" :position="Position.Right" class="rf-handle" />
  </div>
</template>

<style scoped>
.rf-node-vf {
  width: 220px; padding: 10px 14px;
  border-radius: var(--cpq-radius-md, 12px);
  cursor: grab;
}
.rf-node--cfg { border-color: var(--cpq-glass-border-strong) !important; }
.rf-head { display: flex; align-items: center; justify-content: space-between; }
.rf-key {
  font-size: 11px; font-family: ui-monospace, monospace;
  color: var(--cpq-text-muted); text-transform: lowercase; letter-spacing: .5px;
}
.rf-cfg-tag {
  font-size: 10px; padding: 0 6px; border-radius: 6px;
  background: var(--cpq-overlay-w10); color: var(--cpq-accent-primary);
}
.rf-head-tags { display: flex; align-items: center; gap: 4px; }
.rf-badge {
  font-size: 10px; padding: 0 6px; border-radius: 6px;
  background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary);
  font-weight: 600;
}
/* 试运行节点高亮：running 蓝边发光 / done 绿边 */
.rf-node--running {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 16px var(--cpq-overlay-a20);
}
.rf-node--done { border-color: var(--cpq-color-success) !important; }
/* 路径回溯：生成链节点高亮特写，其余变暗 */
.rf-node--trace { border-color: var(--cpq-accent-primary) !important; box-shadow: 0 0 20px var(--cpq-overlay-a20); }
.rf-node--dim { opacity: 0.3; }
.rf-label { font-weight: 600; color: var(--cpq-text-primary); margin-top: 4px; font-size: 14px; }
.rf-desc { font-size: 12px; color: var(--cpq-text-secondary); margin-top: 4px; line-height: 1.45; }
.rf-sources { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.rf-source {
  font-size: 10px; padding: 1px 6px; border-radius: 6px;
  background: var(--cpq-overlay-w8); color: var(--cpq-accent-primary);
}
.rf-handle {
  width: 10px !important; height: 10px !important;
  background: var(--cpq-accent-primary, #1677FF) !important;
  border: 2px solid var(--cpq-glass-3-bg, #fff) !important;
}
</style>
