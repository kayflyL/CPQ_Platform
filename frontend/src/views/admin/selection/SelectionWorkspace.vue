<script setup lang="ts">
/** 选型配置工作台(/strategies/selection)—— 模块工作台 shell。
 *  头部:← 策略中心 + 选型配置 + [🏗 机箱能力 | 🔗 配件适配 | 🛠 兼容规则 | 📄 文档库] 模式开关。
 *
 *  四标签呼应「机箱选型 + 硬件搭配」两分法 + 文档：
 *   🏗 机箱能力：base_config 能力档案编辑(电源槽/后面板槽位/GPU槽/TDP)——兑现「一切前端可配置」。
 *   🔗 配件适配：机箱能力 × 配件 specs 适用系列(L1 声明式适配)可视化探查。
 *   🛠 兼容规则：CRE 卡片+编辑弹窗+拓扑(跨件 require/exclude/derive/recommend,改即生效)。
 *   📄 文档库：选型配置专属文档(module=selection,与报价策略文档库独立)。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { Strategy } from '@/api/strategies'
import PolicyLibrary from '../pricing/PolicyLibrary.vue'
import DocReaderOverlay from '../pricing/DocReaderOverlay.vue'
import CompatibilityRuleEditor from '../CompatibilityRuleEditor.vue'
import ChassisCapabilityEditor from './ChassisCapabilityEditor.vue'
import PartFitMatrix from './PartFitMatrix.vue'

const router = useRouter()
type Mode = 'capability' | 'matrix' | 'engine' | 'docs'
const mode = ref<Mode>('capability')
const readerDoc = ref<Strategy | null>(null)

function openReader(d: Strategy) { readerDoc.value = d }
</script>

<template>
  <div class="sw">
    <div class="sw-bar glass-light">
      <a class="sw-back" @click="router.push('/strategies')">
        <span class="sw-arrow">←</span> 策略中心
      </a>
      <span class="sw-sep">/</span>
      <span class="sw-title">选型配置</span>
      <div class="sw-toggle">
        <a-radio-group v-model:value="mode" button-style="solid" size="small">
          <a-radio-button value="capability">🏗 机箱能力</a-radio-button>
          <a-radio-button value="matrix">🔗 配件适配</a-radio-button>
          <a-radio-button value="engine">🛠 兼容规则</a-radio-button>
          <a-radio-button value="docs">📄 文档库</a-radio-button>
        </a-radio-group>
      </div>
    </div>

    <div class="sw-body">
      <ChassisCapabilityEditor v-if="mode === 'capability'" />
      <PartFitMatrix v-else-if="mode === 'matrix'" />
      <CompatibilityRuleEditor v-else-if="mode === 'engine'" />
      <PolicyLibrary v-else-if="mode === 'docs'" module="selection" @open-doc="openReader" />
    </div>

    <DocReaderOverlay :doc="readerDoc" @close="readerDoc = null" />
  </div>
</template>

<style scoped>
.sw { display: flex; flex-direction: column; padding: 8px 24px 40px; }
.sw-bar {
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
.sw-back {
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: color 0.15s;
  user-select: none;
  white-space: nowrap;
}
.sw-back:hover { color: var(--cpq-accent-primary); }
.sw-arrow { margin-right: 2px; }
.sw-sep { color: var(--cpq-text-disabled); }
.sw-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary); }
.sw-toggle { margin-left: auto; }
.sw-body { flex: 1; min-height: 0; }
</style>
