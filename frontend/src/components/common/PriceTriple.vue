<script setup lang="ts">
/** 价格三联：成本 / 利润率 / 售价 — 机箱卡尾与 KP 大卡头复用，强制同口径。
 *  成本槽：KP 只读 / L6 可编辑(底价,可被手开开关禁用)。
 *  利率槽：可编辑，margin=undefined 时显 placeholder(如「多种」表 KP 利率不一致)。
 *  售价槽：只读，挂 cpq-stream-edge 作 signature 重音。 */
import CountNumber from '@/components/common/CountNumber.vue'

defineProps<{
  cost: number
  margin?: number
  finalPrice: number
  costEditable?: boolean
  costDisabled?: boolean
  marginPlaceholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:margin', v: number): void
  (e: 'update:cost', v: number): void
}>()
</script>

<template>
  <div class="price-triple">
    <!-- 成本 -->
    <div class="pt-cell">
      <span class="pt-label">成本</span>
      <div class="pt-cost-row">
        <a-input-number
          v-if="costEditable"
          :value="cost"
          :disabled="costDisabled"
          :min="0" :precision="2" :step="100"
          size="small" class="pt-num"
          @change="(v: any) => emit('update:cost', Number(v) || 0)"
        />
        <span v-else class="pt-readonly">¥{{ cost.toLocaleString() }}</span>
        <slot name="cost-extra" />
      </div>
    </div>

    <span class="pt-sep" />

    <!-- 利润率 -->
    <div class="pt-cell">
      <span class="pt-label">利润率</span>
      <a-input-number
        :value="margin"
        :min="0" :max="100" :precision="1" :step="1"
        size="small" class="pt-num pt-num-margin"
        :placeholder="marginPlaceholder"
        addon-after="%"
        @change="(v: any) => emit('update:margin', Number(v) || 0)"
      />
    </div>

    <span class="pt-arrow">→</span>

    <!-- 售价（signature 重音）-->
    <div class="pt-cell pt-final-cell">
      <span class="pt-label">售价</span>
      <span class="pt-final">¥<CountNumber :value="finalPrice" /></span>
    </div>
  </div>
</template>

<style scoped>
.price-triple {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  flex-wrap: wrap;
}
.pt-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.pt-label {
  font-size: 10px;
  color: var(--cpq-text-muted, #6E7582);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.pt-cost-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pt-num { width: 130px; }
.pt-num-margin { width: 110px; }
.pt-num :deep(.ant-input-number-input) {
  background: transparent !important;
  color: var(--cpq-text-primary, #E8ECEF) !important;
  font-size: 13px;
}
.pt-readonly {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-secondary, #9BA1AA);
  font-variant-numeric: tabular-nums;
  line-height: 28px;
}
.pt-sep {
  width: 1px;
  align-self: stretch;
  margin: 4px 0;
  background: var(--cpq-overlay-w10, rgba(255, 255, 255, 0.1));
}
.pt-arrow {
  color: var(--cpq-text-muted, #6E7582);
  font-size: 14px;
  line-height: 28px;
  padding-bottom: 2px;
}
.pt-final-cell {
  margin-left: auto;
  align-items: flex-end;
}
.pt-final {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  font-size: 18px;
  font-weight: 700;
  color: var(--cpq-accent-primary, #1677FF);
  font-variant-numeric: tabular-nums;
  line-height: 28px;
  padding: 0 4px;
}
</style>
