<script setup lang="ts">
/** 报价策略工作台(/strategies/pricing)—— 模块工作台 shell。
 *  头部:← 策略中心 + 报价策略 + [📄 文档库 | 🛠 定价引擎] 模式开关。
 *  文档库模式:挂 PolicyLibrary(分类目录+卡片网格),点卡 → DocReaderOverlay 呼吸浮窗。
 *  定价引擎模式:挂现有 PricingFlowCanvas(画布+演算器,零改)。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { Strategy } from '@/api/strategies'
import PolicyLibrary from './PolicyLibrary.vue'
import PricingFlowCanvas from './PricingFlowCanvas.vue'
import DocReaderOverlay from './DocReaderOverlay.vue'

const router = useRouter()
const mode = ref<'docs' | 'engine'>('docs')
const readerDoc = ref<Strategy | null>(null)

function openReader(d: Strategy) { readerDoc.value = d }
</script>

<template>
  <div class="pw">
    <div class="pw-bar glass-light">
      <a class="pw-back" @click="router.push('/strategies')">
        <span class="pw-arrow">←</span> 策略中心
      </a>
      <span class="pw-sep">/</span>
      <span class="pw-title">报价策略</span>
      <div class="pw-toggle">
        <a-radio-group v-model:value="mode" button-style="solid" size="small">
          <a-radio-button value="docs">📄 文档库</a-radio-button>
          <a-radio-button value="engine">🛠 定价引擎</a-radio-button>
        </a-radio-group>
      </div>
    </div>

    <div class="pw-body">
      <PolicyLibrary v-if="mode === 'docs'" module="pricing" @open-doc="openReader" />
      <PricingFlowCanvas v-else-if="mode === 'engine'" />
    </div>

    <DocReaderOverlay :doc="readerDoc" @close="readerDoc = null" />
  </div>
</template>

<style scoped>
.pw { display: flex; flex-direction: column; padding: 8px 24px 40px; }
.pw-bar {
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
.pw-back {
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: color 0.15s;
  user-select: none;
  white-space: nowrap;
}
.pw-back:hover { color: var(--cpq-accent-primary); }
.pw-arrow { margin-right: 2px; }
.pw-sep { color: var(--cpq-text-disabled); }
.pw-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary); }
.pw-toggle { margin-left: auto; }
.pw-body { flex: 1; min-height: 0; }
</style>
