<template>
  <div class="l6-config-wizard" :class="{ compact }">
    <!-- Steps -->
    <a-steps :current="currentStep" size="small" class="config-steps">
      <a-step title="基准配置" />
      <a-step title="前面板" />
      <a-step title="后面板" />
      <a-step title="电源" />
    </a-steps>

    <!-- Step Content -->
    <div class="step-content">
      <!-- Step 1: 基准配置 -->
      <div v-if="currentStep === 0" class="step-panel">
        <div class="filter-row">
          <a-select v-model:value="filterChassis" placeholder="机箱" allow-clear size="small" style="width: 120px;" @change="onFilterChange">
            <a-select-option v-for="v in distinctChassis" :key="v" :value="v">{{ v }}</a-select-option>
          </a-select>
          <a-select v-model:value="filterSeries" placeholder="系列" allow-clear size="small" style="width: 120px;" @change="onFilterChange">
            <a-select-option v-for="v in distinctSeries" :key="v" :value="v">{{ v }}</a-select-option>
          </a-select>
          <a-select v-model:value="filterDriveBays" placeholder="盘位" allow-clear size="small" style="width: 100px;" @change="onFilterChange">
            <a-select-option v-for="v in filteredDriveBays" :key="v" :value="v">{{ v }}</a-select-option>
          </a-select>
          <a-select v-model:value="filterBackplane" placeholder="背板" allow-clear size="small" style="width: 140px;" @change="onFilterChange">
            <a-select-option v-for="v in filteredBackplaneTypes" :key="v" :value="v">{{ v }}</a-select-option>
          </a-select>
        </div>
        <a-table
          :columns="baseConfigColumns"
          :data-source="filteredBaseConfigs"
          :row-selection="{ type: 'radio', selectedRowKeys: selectedBaseConfigId ? [selectedBaseConfigId] : [], onChange: onSelectBaseConfig }"
          row-key="config_id"
          :pagination="false"
          size="small"
          :scroll="{ y: compact ? 200 : 360 }"
        />
      </div>

      <!-- Step 2: 前面板 -->
      <div v-if="currentStep === 1" class="step-panel">
        <a-table
          :columns="frontPanelColumns"
          :data-source="filteredFrontPanelItems"
          :row-selection="{ type: 'radio', selectedRowKeys: selectedFrontPanelId ? [selectedFrontPanelId] : [], onChange: onSelectFrontPanel }"
          row-key="item_id"
          :pagination="false"
          size="small"
          :scroll="{ y: compact ? 240 : 400 }"
        />
      </div>

      <!-- Step 3: 后面板 -->
      <div v-if="currentStep === 2" class="step-panel">
        <a-table
          :columns="rearPanelColumns"
          :data-source="filteredRearPanelItems"
          :row-selection="{ type: 'radio', selectedRowKeys: selectedRearPanelId ? [selectedRearPanelId] : [], onChange: onSelectRearPanel }"
          row-key="item_id"
          :pagination="false"
          size="small"
          :scroll="{ y: compact ? 240 : 400 }"
        />
      </div>

      <!-- Step 4: 电源 -->
      <div v-if="currentStep === 3" class="step-panel">
        <a-table
          :columns="psuColumns"
          :data-source="filteredPsuOptions"
          :row-selection="{ type: 'radio', selectedRowKeys: selectedPsuId ? [selectedPsuId] : [], onChange: onSelectPsu }"
          row-key="psu_id"
          :pagination="false"
          size="small"
          :scroll="{ y: compact ? 240 : 400 }"
        />
      </div>
    </div>

    <!-- Step Actions -->
    <div class="step-actions">
      <a-button v-if="currentStep > 0" @click="currentStep--">← 上一步</a-button>
      <div class="step-spacer"></div>
      <a-button v-if="currentStep < 3" type="primary" @click="currentStep++" :disabled="!canProceed">下一步 →</a-button>
      <a-button v-if="currentStep === 3" type="primary" @click="handleSave" :disabled="!canProceed">✓ 保存配置</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useL6ChassisConfig } from '@/composables/useL6ChassisConfig'

const props = defineProps<{
  compact?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', config: any): void
}>()

// 复用 L6 机箱配置逻辑
const {
  baseConfigs,
  selectedBaseConfigId,
  selectedFrontPanelId,
  selectedRearPanelId,
  selectedPsuId,
  selectedBaseConfig,
  selectedFrontPanel,
  selectedRearPanel,
  selectedPsu,
  filteredFrontPanelItems,
  filteredRearPanelItems,
  filteredPsuOptions,
  refreshAll,
  onSelectBaseConfig,
  onSelectFrontPanel,
  onSelectRearPanel,
  onSelectPsu,
  baseConfigPrice,
  frontPanelPrice,
  rearPanelPrice,
  psuPrice,
  frontPanelQty,
  rearPanelQty,
  psuQty,
  resetSelections
} = useL6ChassisConfig()

// UI 状态
const currentStep = ref(0)

// 筛选器
const filterChassis = ref<string>()
const filterSeries = ref<string>()
const filterDriveBays = ref<string>()
const filterBackplane = ref<string>()

// 级联筛选：去重值
const distinctChassis = computed(() => {
  const set = new Set(baseConfigs.value.map(c => c.chassis).filter(Boolean))
  return Array.from(set).sort()
})

const distinctSeries = computed(() => {
  let list = baseConfigs.value
  if (filterChassis.value) {
    list = list.filter(c => c.chassis === filterChassis.value)
  }
  const set = new Set(list.map(c => c.chassis_series).filter(Boolean))
  return Array.from(set).sort()
})

const filteredDriveBays = computed(() => {
  let list = baseConfigs.value
  if (filterChassis.value) {
    list = list.filter(c => c.chassis === filterChassis.value)
  }
  if (filterSeries.value) {
    list = list.filter(c => c.chassis_series === filterSeries.value)
  }
  const set = new Set(list.map(c => c.drive_bays).filter(Boolean))
  return Array.from(set).sort()
})

const filteredBackplaneTypes = computed(() => {
  let list = baseConfigs.value
  if (filterChassis.value) {
    list = list.filter(c => c.chassis === filterChassis.value)
  }
  if (filterSeries.value) {
    list = list.filter(c => c.chassis_series === filterSeries.value)
  }
  if (filterDriveBays.value) {
    list = list.filter(c => c.drive_bays === filterDriveBays.value)
  }
  const set = new Set(list.map(c => c.backplane_type).filter(Boolean))
  return Array.from(set).sort()
})

// 过滤后的基准配置
const filteredBaseConfigs = computed(() => {
  return baseConfigs.value.filter(c => {
    if (filterChassis.value && c.chassis !== filterChassis.value) return false
    if (filterSeries.value && c.chassis_series !== filterSeries.value) return false
    if (filterDriveBays.value && c.drive_bays !== filterDriveBays.value) return false
    if (filterBackplane.value && c.backplane_type !== filterBackplane.value) return false
    return true
  })
})

// 级联筛选清理
const onFilterChange = () => {
  if (filterDriveBays.value && !filteredDriveBays.value.includes(filterDriveBays.value)) {
    filterDriveBays.value = undefined
  }
  if (filterBackplane.value && !filteredBackplaneTypes.value.includes(filterBackplane.value)) {
    filterBackplane.value = undefined
  }
}

// 是否可以继续
const canProceed = computed(() => {
  if (currentStep.value === 0) return !!selectedBaseConfigId.value
  if (currentStep.value === 1) return !!selectedFrontPanelId.value
  if (currentStep.value === 2) return !!selectedRearPanelId.value
  if (currentStep.value === 3) return !!selectedPsuId.value
  return false
})

// 表格列定义
const baseConfigColumns = [
  { title: '机箱', dataIndex: 'chassis', key: 'chassis', width: 80 },
  { title: '系列', dataIndex: 'chassis_series', key: 'chassis_series', width: 100 },
  { title: '盘位', dataIndex: 'drive_bays', key: 'drive_bays', width: 70 },
  { title: '背板', dataIndex: 'backplane_type', key: 'backplane_type', width: 120, ellipsis: true },
  { title: '价格', dataIndex: 'base_price', key: 'base_price', width: 100, customRender: ({ text }: any) => `¥${formatPrice(text)}` }
]

const frontPanelColumns = [
  { title: '类型', dataIndex: 'cable_type', key: 'cable_type', width: 100 },
  { title: '名称', dataIndex: 'part_name', key: 'part_name', width: 200, ellipsis: true },
  { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  { title: '价格', dataIndex: 'unit_price', key: 'unit_price', width: 100, customRender: ({ text }: any) => `¥${formatPrice(text)}` }
]

const rearPanelColumns = [
  { title: '类型', dataIndex: 'option_type', key: 'option_type', width: 100 },
  { title: '名称', dataIndex: 'part_name', key: 'part_name', width: 200, ellipsis: true },
  { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  { title: '价格', dataIndex: 'unit_price', key: 'unit_price', width: 100, customRender: ({ text }: any) => `¥${formatPrice(text)}` }
]

const psuColumns = [
  { title: '功率', dataIndex: 'wattage', key: 'wattage', width: 100 },
  { title: '名称', dataIndex: 'part_name', key: 'part_name', width: 200, ellipsis: true },
  { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  { title: '价格', dataIndex: 'unit_price', key: 'unit_price', width: 100, customRender: ({ text }: any) => `¥${formatPrice(text)}` }
]

function formatPrice(price: number): string {
  if (isNaN(price)) return '—'
  return price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleSave() {
  if (!canProceed.value) return

  emit('save', {
    base_config: selectedBaseConfig.value,
    front_panel: selectedFrontPanel.value,
    rear_panel: selectedRearPanel.value,
    psu: selectedPsu.value,
    front_panel_qty: frontPanelQty.value,
    rear_panel_qty: rearPanelQty.value,
    psu_qty: psuQty.value,
    base_price: baseConfigPrice.value,
    front_panel_price: frontPanelPrice.value,
    rear_panel_price: rearPanelPrice.value,
    psu_price: psuPrice.value,
    total_price: baseConfigPrice.value + frontPanelPrice.value + rearPanelPrice.value + psuPrice.value
  })
}

// 重置向导
function reset() {
  currentStep.value = 0
  resetSelections()
  filterChassis.value = undefined
  filterSeries.value = undefined
  filterDriveBays.value = undefined
  filterBackplane.value = undefined
}

// 初始化加载数据
onMounted(() => {
  refreshAll()
})

// 暴露方法和属性
defineExpose({
  reset,
  refreshAll,
  basePrice: baseConfigPrice,
  frontPanelPrice,
  rearPanelPrice,
  psuPrice,
  frontPanelQty,
  rearPanelQty,
  psuQty,
  selectedBaseConfig,
  selectedFrontPanel,
  selectedRearPanel,
  selectedPsu
})
</script>

<style scoped>
.l6-config-wizard {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.config-steps {
  margin-bottom: 16px;
}

.step-content {
  flex: 1;
  overflow: hidden;
}

.step-panel {
  height: 100%;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.step-actions {
  display: flex;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--cpq-border);
  margin-top: 12px;
}

.step-spacer {
  flex: 1;
}

/* Compact mode */
.l6-config-wizard.compact .config-steps {
  margin-bottom: 12px;
}

.l6-config-wizard.compact .filter-row {
  margin-bottom: 8px;
}

.l6-config-wizard.compact .step-actions {
  padding-top: 8px;
  margin-top: 8px;
}
</style>
