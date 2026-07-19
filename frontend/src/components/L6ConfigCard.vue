<template>
  <div class="l6-price-card glass">
    <!-- Header -->
    <div class="card-header">
      <div class="header-left">
        <span class="card-title">L6 机箱配置</span>
        <a-tag v-if="hasConfig" color="green" size="small">已配置</a-tag>
        <a-tag v-else color="orange" size="small">未配置</a-tag>
      </div>
      <div class="header-right" v-if="hasConfig">
        <a-button type="link" size="small" @click="handleReset">重新配置</a-button>
      </div>
    </div>

    <!-- Wizard -->
    <div class="wizard-container">
      <L6ConfigWizard ref="wizardRef" compact @save="handleWizardSave" />
    </div>

    <!-- Config Summary Table (始终显示) -->
    <div class="config-summary">
      <div class="summary-title">配置摘要</div>
      <table class="summary-table">
        <thead>
          <tr>
            <th>类别</th>
            <th>名称</th>
            <th>描述</th>
            <th>数量</th>
            <th>单价</th>
            <th>总价</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="category">基准底盘</td>
            <td>{{ wizardBaseConfig?.chassis || '—' }}</td>
            <td>{{ wizardBaseConfig?.description || '—' }}</td>
            <td>1</td>
            <td>¥ {{ formatPrice(wizardBasePrice) }}</td>
            <td>¥ {{ formatPrice(wizardBasePrice) }}</td>
          </tr>
          <tr>
            <td class="category">前面板</td>
            <td>{{ wizardFrontPanel?.part_name || '—' }}</td>
            <td>{{ wizardFrontPanel?.description || '—' }}</td>
            <td><a-input-number v-model:value="frontPanelQty" :min="1" :max="99" size="small" style="width: 60px" /></td>
            <td>¥ {{ formatPrice(wizardFrontPanelUnitPrice) }}</td>
            <td>¥ {{ formatPrice(wizardFrontPanelPrice) }}</td>
          </tr>
          <tr>
            <td class="category">后面板</td>
            <td>{{ wizardRearPanel?.part_name || '—' }}</td>
            <td>{{ wizardRearPanel?.description || '—' }}</td>
            <td><a-input-number v-model:value="rearPanelQty" :min="1" :max="99" size="small" style="width: 60px" /></td>
            <td>¥ {{ formatPrice(wizardRearPanelUnitPrice) }}</td>
            <td>¥ {{ formatPrice(wizardRearPanelPrice) }}</td>
          </tr>
          <tr>
            <td class="category">电源</td>
            <td>{{ wizardPsu?.part_name || '—' }}</td>
            <td>{{ wizardPsu?.description || '—' }}</td>
            <td><a-input-number v-model:value="psuQty" :min="1" :max="99" size="small" style="width: 60px" /></td>
            <td>¥ {{ formatPrice(wizardPsuUnitPrice) }}</td>
            <td>¥ {{ formatPrice(wizardPsuPrice) }}</td>
          </tr>
          <tr v-if="hasAnySelection" class="total-row">
            <td colspan="5" class="total-label">合计</td>
            <td class="total-value">¥ {{ formatPrice(calculatedTotal) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Price Adjustment (常驻显示) -->
    <div class="price-adjust">
      <div class="adjust-row">
        <label>自定义价格</label>
        <a-input-number
          :value="savedConfig ? customPrice : undefined"
          @change="(v: number) => $emit('priceChange', v || 0)"
          :precision="2"
          size="small"
          style="width: 120px"
          placeholder="保存配置后填入"
        />
      </div>
      <div class="adjust-row">
        <label>利润率 %</label>
        <a-input-number
          :value="profitMargin"
          @change="(v: number) => $emit('marginChange', v || 0)"
          :min="0"
          :max="100"
          :precision="1"
          size="small"
          style="width: 100px"
        />
      </div>
      <div class="adjust-row final">
        <label>最终售价</label>
        <span class="final-value">{{ savedConfig ? `¥ ${formatPrice(finalPrice)}` : '—' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import L6ConfigWizard from './L6ConfigWizard.vue'

const props = defineProps<{
  mode?: 'upload' | 'create'
  basePrice?: number
  frontPanelPrice?: number
  rearPanelPrice?: number
  psuPrice?: number
  customPrice?: number
  profitMargin?: number
}>()

const emit = defineEmits<{
  (e: 'configure', config: any): void
  (e: 'priceChange', price: number): void
  (e: 'marginChange', margin: number): void
}>()

const wizardRef = ref<InstanceType<typeof L6ConfigWizard> | null>(null)
const savedConfig = ref<any>(null)

// 从 wizard 实时获取选中项（用于配置摘要的名称/描述）
const wizardBaseConfig = computed(() => wizardRef.value?.selectedBaseConfig || null)
const wizardFrontPanel = computed(() => wizardRef.value?.selectedFrontPanel || null)
const wizardRearPanel = computed(() => wizardRef.value?.selectedRearPanel || null)
const wizardPsu = computed(() => wizardRef.value?.selectedPsu || null)

// 从 wizard 实时获取价格（用于配置摘要）
const wizardBasePrice = computed(() => wizardRef.value?.basePrice || 0)
const wizardFrontPanelPrice = computed(() => wizardRef.value?.frontPanelPrice || 0)
const wizardRearPanelPrice = computed(() => wizardRef.value?.rearPanelPrice || 0)
const wizardPsuPrice = computed(() => wizardRef.value?.psuPrice || 0)

// 从 wizard 实时获取单价（用于摘要表显示）
const wizardFrontPanelUnitPrice = computed(() => wizardRef.value?.selectedFrontPanel?.unit_price || 0)
const wizardRearPanelUnitPrice = computed(() => wizardRef.value?.selectedRearPanel?.unit_price || 0)
const wizardPsuUnitPrice = computed(() => wizardRef.value?.selectedPsu?.unit_price || 0)

// 数量（双向绑定到 wizard composable）
const frontPanelQty = computed({
  get: () => wizardRef.value?.frontPanelQty ?? 1,
  set: (v: number) => { if (wizardRef.value) wizardRef.value.frontPanelQty = v || 1 }
})
const rearPanelQty = computed({
  get: () => wizardRef.value?.rearPanelQty ?? 1,
  set: (v: number) => { if (wizardRef.value) wizardRef.value.rearPanelQty = v || 1 }
})
const psuQty = computed({
  get: () => wizardRef.value?.psuQty ?? 1,
  set: (v: number) => { if (wizardRef.value) wizardRef.value.psuQty = v || 1 }
})

// 是否有任何选中项（用于显示合计行）
const hasAnySelection = computed(() => {
  return wizardBaseConfig.value || wizardFrontPanel.value || wizardRearPanel.value || wizardPsu.value
})

// 配置摘要的实时合计
const calculatedTotal = computed(() => {
  return wizardBasePrice.value + wizardFrontPanelPrice.value + wizardRearPanelPrice.value + wizardPsuPrice.value
})

const finalPrice = computed(() => {
  if (!savedConfig.value) return 0
  const price = props.customPrice || savedConfig.value.total_price
  const margin = props.profitMargin || 0
  return price * (1 + margin / 100)
})

const hasConfig = computed(() => !!savedConfig.value)

function formatPrice(price: number | undefined): string {
  if (!price || isNaN(price)) return '0.00'
  return price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleWizardSave(config: any) {
  savedConfig.value = config
  emit('configure', config)
}

function handleReset() {
  wizardRef.value?.reset()
  savedConfig.value = null
  emit('priceChange', 0)  // 清空自定义价格，利润率不动
}
</script>

<style scoped>
.l6-price-card {
  padding: 16px;
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.wizard-container {
  margin-bottom: 16px;
}

/* Config Summary */
.config-summary {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--cpq-bg-secondary);
  border-radius: 8px;
}

.summary-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  margin-bottom: 8px;
}

.summary-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.summary-table th,
.summary-table td {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid var(--cpq-border-primary);
}

.summary-table th {
  font-weight: 600;
  color: var(--cpq-text-secondary);
  background: var(--cpq-bg-tertiary);
}

.summary-table td.category {
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.summary-table td:nth-child(4),
.summary-table td:nth-child(5),
.summary-table td:nth-child(6) {
  text-align: right;
  font-family: 'Courier New', monospace;
}

.summary-table th:nth-child(4),
.summary-table th:nth-child(5),
.summary-table th:nth-child(6) {
  text-align: right;
}

.total-row td {
  font-weight: 700;
  border-top: 2px solid var(--cpq-border-primary);
}

.total-row .total-label {
  text-align: right;
  color: var(--cpq-text-primary);
}

.total-row .total-value {
  text-align: right;
  font-family: 'Courier New', monospace;
  color: var(--cpq-accent-primary);
  font-size: 14px;
}

/* Price Adjustment */
.price-adjust {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px;
  background: var(--cpq-bg-secondary);
  border-radius: 8px;
}

.adjust-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.adjust-row label {
  font-size: 11px;
  color: var(--cpq-text-tertiary);
}

.adjust-row.final {
  margin-left: auto;
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

.adjust-row.final label {
  font-size: 13px;
  color: var(--cpq-text-secondary);
  font-weight: 500;
}

.final-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  font-family: 'Courier New', monospace;
}
</style>
