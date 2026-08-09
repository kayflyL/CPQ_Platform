<script setup lang="ts">
/** vue flow 自定义节点（注册名 rf）。复用 Glass Console 玻璃卡样式 + 左右 Handle。
 *  data 由 ReasoningFlowCanvas 注入：{ stepType, label, configurable }。
 *  元数据（中文名/职能/来源/图标）统一读 utils/reasoningNodeMeta（palette/节点卡/抽屉共用真源）。 */
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { reasoningNodeMeta } from '@/utils/reasoningNodeMeta'

const props = defineProps<{ id: string; data: any }>()
const stepType = computed(() => props.data?.stepType || '')
const meta = computed(() => reasoningNodeMeta(stepType.value))
const showName = computed(() => meta.value?.name || props.data?.label || stepType.value)
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
      <span class="rf-icon ni-chip" :class="`ni--${meta?.tone || 'gray'}`" v-if="meta?.icon">
        <component :is="meta.icon" />
      </span>
      <span class="rf-key">{{ stepType }}</span>
      <div class="rf-head-tags">
        <span v-if="data?.badge" class="rf-badge">{{ data.badge }}</span>
        <span v-if="meta?.fallback" class="rf-cfg-tag rf-tag--fallback" title="AI 失效时才走的兜底节点">兜底</span>
        <span v-if="data?.configurable" class="rf-cfg-tag">可配置</span>
      </div>
    </div>
    <div class="rf-label">{{ showName }}</div>
    <div class="rf-desc">{{ meta?.desc }}</div>
    <div v-if="meta?.sources?.length" class="rf-sources">
      <span v-for="s in meta.sources" :key="s" class="rf-source">{{ s }}</span>
    </div>
    <!-- condition 节点：双出口 Handle（真=true 上 / 假=false 下）；其余节点单出口 -->
    <template v-if="stepType === 'condition'">
      <Handle id="true" type="source" :position="Position.Right" class="rf-handle rf-handle--branch" style="top: 28%;" />
      <Handle id="false" type="source" :position="Position.Right" class="rf-handle rf-handle--branch" style="top: 72%;" />
      <span class="rf-handle-label rf-handle-label--true">真</span>
      <span class="rf-handle-label rf-handle-label--false">假</span>
    </template>
    <Handle v-else type="source" :position="Position.Right" class="rf-handle" />
  </div>
</template>

<style scoped>
.rf-node-vf {
  width: 220px; padding: 10px 14px;
  border-radius: var(--cpq-radius-md, 12px);
  cursor: grab;
  position: relative;
}
.rf-node--cfg { border-color: var(--cpq-glass-border-strong) !important; }
.rf-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.rf-icon { width: 26px; height: 26px; font-size: 14px; border-radius: 7px; }
.rf-icon :deep(svg) { width: 15px; height: 15px; }
.rf-key {
  font-size: 11px; font-family: ui-monospace, monospace;
  color: var(--cpq-text-muted); text-transform: lowercase; letter-spacing: .5px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rf-cfg-tag {
  font-size: 10px; padding: 0 6px; border-radius: 6px;
  background: var(--cpq-overlay-w10); color: var(--cpq-accent-primary);
}
.rf-tag--fallback { background: rgba(250, 140, 22, 0.14); color: var(--cpq-accent-warning, #fa8c16); }
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

/* 节点图标软底色块（与 palette 共用同一套 ni-- 色调） */
.ni-chip {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: var(--cpq-radius-sm, 8px);
  font-size: 15px; flex-shrink: 0;
}
.ni-chip.ni--blue { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.ni-chip.ni--purple { background: rgba(168, 85, 247, 0.12); color: var(--cpq-color-purple, #a855f7); }
.ni-chip.ni--green { background: var(--cpq-overlay-success15); color: var(--cpq-color-success, #52C9A0); }
.ni-chip.ni--orange { background: rgba(250, 140, 22, 0.12); color: var(--cpq-color-orange, #fa8c16); }
.ni-chip.ni--cyan { background: var(--cpq-overlay-cyan15); color: var(--cpq-accent-cyan, #36CFCF); }
.ni-chip.ni--gray { background: var(--cpq-overlay-w8); color: var(--cpq-text-muted); }
/* condition 双出口标签（真/假分支） */
.rf-handle-label { position: absolute; right: 18px; font-size: 9px; line-height: 1; pointer-events: none; }
.rf-handle-label--true { top: 25%; color: var(--cpq-color-success); }
.rf-handle-label--false { top: 69%; color: var(--cpq-accent-warning, #fa8c16); }
</style>
