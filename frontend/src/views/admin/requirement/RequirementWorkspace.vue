<script setup lang="ts">
/** 需求分析工作台(/strategies/requirement)—— 模块工作台 shell（对齐选型配置/报价策略）。
 *  头部:← 策略中心 + 需求分析 + [🛠 推理流 | 📄 文档库] 模式开关。
 *  推理流模式:挂 ReasoningFlowCanvas（DAG 编排 + 试运行,零改）。
 *  文档库模式:挂 PolicyLibrary(module=requirement),点卡 → DocReaderOverlay 呼吸浮窗。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { PolicyDoc } from '@/api/strategies'
import PolicyLibrary from '../pricing/PolicyLibrary.vue'
import DocReaderOverlay from '../pricing/DocReaderOverlay.vue'
import ReasoningFlowCanvas from '../reasoning/ReasoningFlowCanvas.vue'

const router = useRouter()
type Mode = 'engine' | 'docs'
const mode = ref<Mode>('engine')
const readerDoc = ref<PolicyDoc | null>(null)

function openReader(d: PolicyDoc) { readerDoc.value = d }
</script>

<template>
  <div class="rw">
    <div class="rw-bar glass-light">
      <a class="rw-back" @click="router.push('/strategies')">
        <span class="rw-arrow">←</span> 策略中心
      </a>
      <span class="rw-sep">/</span>
      <span class="rw-title">需求分析</span>
      <div class="rw-toggle">
        <a-radio-group v-model:value="mode" button-style="solid" size="small">
          <a-radio-button value="engine">🛠 推理流</a-radio-button>
          <a-radio-button value="docs">📄 文档库</a-radio-button>
        </a-radio-group>
      </div>
    </div>

    <div class="rw-body">
      <ReasoningFlowCanvas v-if="mode === 'engine'" />
      <PolicyLibrary v-else-if="mode === 'docs'" module="requirement" @open-doc="openReader" />
    </div>

    <DocReaderOverlay :doc="readerDoc" @close="readerDoc = null" />
  </div>
</template>

<style scoped>
.rw { display: flex; flex-direction: column; padding: 8px 24px 40px; }
.rw-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  border-radius: 12px;
  border: 1px solid var(--cpq-glass-border);
  margin-bottom: 16px;
  position: sticky;
  top: 12px;
  z-index: 5;
}
.rw-back {
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: color 0.15s;
  user-select: none;
  white-space: nowrap;
}
.rw-back:hover { color: var(--cpq-accent-primary); }
.rw-arrow { margin-right: 2px; }
.rw-sep { color: var(--cpq-text-disabled); }
.rw-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary); }
.rw-toggle { margin-left: auto; }
.rw-body { flex: 1; min-height: 0; }
</style>
