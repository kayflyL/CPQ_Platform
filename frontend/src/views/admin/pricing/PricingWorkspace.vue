<script setup lang="ts">
/** 报价策略工作台(/strategies/pricing)—— 模块工作台 shell。
 *  头部:← 解决方案 + 报价策略 + 定价引擎（文档库已迁至解决方案区）。
 *  定价引擎模式:挂现有 PricingFlowCanvas(画布+演算器,零改)。 */
import { useRouter } from 'vue-router'
import PricingFlowCanvas from './PricingFlowCanvas.vue'

const router = useRouter()
</script>

<template>
  <div class="pw">
    <div class="pw-bar glass-light">
      <a class="pw-back" @click="router.push('/strategies')">
        <span class="pw-arrow">←</span> 解决方案
      </a>
      <span class="pw-sep">/</span>
      <span class="pw-title">报价策略</span>
    </div>

    <div class="pw-body">
      <PricingFlowCanvas />
    </div>
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
