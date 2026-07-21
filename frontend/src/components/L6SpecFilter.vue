<template>
  <div class="l6-spec-filter">
    <div class="filter-header">
      <span class="filter-title">📊 五维规格匹配</span>
      <a-button type="text" size="small" @click="clearFilters" v-if="hasActiveFilters">清空筛选</a-button>
    </div>
    <div class="filter-row">
      <a-select v-model:value="filters.chassis" placeholder="机箱" style="width: 140px" allowClear @change="emitFilter">
        <a-select-option v-for="v in uniqueChassis" :key="v" :value="v">{{ v }}</a-select-option>
      </a-select>
      <a-select v-model:value="filters.model" placeholder="机型" style="width: 140px" allowClear @change="emitFilter">
        <a-select-option v-for="v in uniqueModels" :key="v" :value="v">{{ v }}</a-select-option>
      </a-select>
      <a-select v-model:value="filters.drive_bays" placeholder="盘位" style="width: 140px" allowClear @change="emitFilter">
        <a-select-option v-for="v in uniqueDriveBays" :key="v" :value="v">{{ v }}</a-select-option>
      </a-select>
      <a-select v-model:value="filters.psu" placeholder="PSU" style="width: 140px" allowClear @change="emitFilter">
        <a-select-option v-for="v in uniquePsu" :key="v" :value="v">{{ v }}</a-select-option>
      </a-select>
      <a-select v-model:value="filters.motherboard" placeholder="主板" style="width: 140px" allowClear @change="emitFilter">
        <a-select-option v-for="v in uniqueMotherboards" :key="v" :value="v">{{ v }}</a-select-option>
      </a-select>
    </div>
    <!-- Match Result -->
    <div v-if="hasActiveFilters" class="match-result">
      <div v-if="matchedRecords.length === 0" class="match-bar match-error">
        <span class="match-icon">❌</span>
        <span class="match-text">无匹配记录</span>
      </div>
      <div v-else-if="matchedRecords.length === 1" class="match-bar match-success">
        <span class="match-icon">✅</span>
        <span class="match-text">唯一匹配：¥{{ formatPrice(matchedRecords[0].price) }}</span>
        <span class="match-detail">
          （{{ matchedRecords[0].chassis }} + {{ matchedRecords[0].model }} +
          {{ matchedRecords[0].drive_bays }}盘位 + {{ matchedRecords[0].psu }} + {{ matchedRecords[0].motherboard }}）
        </span>
      </div>
      <div v-else class="match-bar match-warning">
        <span class="match-icon">⚠️</span>
        <span class="match-text">多条匹配（{{ matchedRecords.length }}条），匹配的卡片已高亮</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface L6Record {
  id: number
  chassis: string
  model: string
  drive_bays: string
  psu: string
  motherboard: string
  price: number
  [key: string]: any
}

const props = defineProps<{
  records: L6Record[]
}>()

const emit = defineEmits<{
  (e: 'filter-change', matched: L6Record[], hasFilter: boolean, filterValues: { chassis: string | undefined; model: string | undefined; drive_bays: string | undefined; psu: string | undefined; motherboard: string | undefined }): void
}>()

const filters = ref<{ chassis: string | undefined; model: string | undefined; drive_bays: string | undefined; psu: string | undefined; motherboard: string | undefined }>({
  chassis: '',
  model: '',
  drive_bays: '',
  psu: '',
  motherboard: '',
})

const uniqueChassis = computed(() => [...new Set(props.records.map(r => r.chassis).filter(Boolean))])
const uniqueModels = computed(() => [...new Set(props.records.map(r => r.model).filter(Boolean))])
const uniqueDriveBays = computed(() => [...new Set(props.records.map(r => r.drive_bays).filter(Boolean))])
const uniquePsu = computed(() => [...new Set(props.records.map(r => r.psu).filter(Boolean))])
const uniqueMotherboards = computed(() => [...new Set(props.records.map(r => r.motherboard).filter(Boolean))])

const hasActiveFilters = computed(() => {
  return Object.values(filters.value).some(v => v !== '')
})

const matchedRecords = computed(() => {
  if (!hasActiveFilters.value) return []
  return props.records.filter(record => {
    if (filters.value.chassis && record.chassis !== filters.value.chassis) return false
    if (filters.value.model && record.model !== filters.value.model) return false
    if (filters.value.drive_bays && record.drive_bays !== filters.value.drive_bays) return false
    if (filters.value.psu && record.psu !== filters.value.psu) return false
    if (filters.value.motherboard && record.motherboard !== filters.value.motherboard) return false
    return true
  })
})

const formatPrice = (price: number) => price?.toLocaleString() ?? '0'

const emitFilter = () => {
  emit('filter-change', matchedRecords.value, hasActiveFilters.value, { ...filters.value })
}

// 监听数据源变化时重新计算
watch(() => props.records, () => {
  emitFilter()
}, { deep: true })

const clearFilters = () => {
  filters.value = { chassis: '', model: '', drive_bays: '', psu: '', motherboard: '' }
  emitFilter()
}

// 初始化时也 emit 一次
emitFilter()
</script>

<style scoped>
.l6-spec-filter {
  background: var(--cpq-overlay-b20);
  backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-overlay-w8);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 20px;
}
.filter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.filter-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.filter-header :deep(.ant-btn-text) {
  color: var(--cpq-text-muted) !important;
}
.filter-header :deep(.ant-btn-text:hover) {
  color: var(--cpq-accent-primary) !important;
}
.filter-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

/* ===== Select selector ===== */
.l6-spec-filter :deep(.ant-select-selector) {
  background: var(--cpq-overlay-w6) !important;
  border: 1px solid var(--cpq-overlay-w10) !important;
  border-radius: 6px !important;
}
.l6-spec-filter :deep(.ant-select-selection-placeholder) {
  color: var(--cpq-text-muted) !important;
}
.l6-spec-filter :deep(.ant-select-selection-item) {
  color: var(--cpq-text-primary) !important;
}
.l6-spec-filter :deep(.ant-select-selection-search-input) {
  color: var(--cpq-text-primary) !important;
}
/* Hover */
.l6-spec-filter :deep(.ant-select:hover .ant-select-selector) {
  border-color: var(--cpq-overlay-w20) !important;
}
/* Focus */
.l6-spec-filter :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a15) !important;
}

/* ===== Clear button & arrow icon ===== */
.l6-spec-filter :deep(.ant-select-clear),
.l6-spec-filter :deep(.ant-select-arrow) {
  color: var(--cpq-text-muted) !important;
}
.l6-spec-filter :deep(.ant-select-clear:hover),
.l6-spec-filter :deep(.ant-select-arrow:hover) {
  color: var(--cpq-text-secondary) !important;
}

/* ===== Dropdown menu ===== */
.l6-spec-filter :deep(.ant-select-dropdown) {
  background: var(--cpq-bg-secondary) !important;
  border: 1px solid var(--cpq-overlay-w10) !important;
  box-shadow: 0 8px 24px var(--cpq-shadow-color-strong) !important;
}
.l6-spec-filter :deep(.ant-select-item) {
  color: var(--cpq-text-light) !important;
}
.l6-spec-filter :deep(.ant-select-item-option-active) {
  background: var(--cpq-overlay-w6) !important;
}
.l6-spec-filter :deep(.ant-select-item-option-selected) {
  background: var(--cpq-overlay-a10) !important;
  color: var(--cpq-accent-primary) !important;
}

/* ===== Match result bars ===== */
.match-result {
  margin-top: 8px;
}
.match-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  border: 1px solid transparent;
}
.match-icon {
  flex-shrink: 0;
}
.match-text {
  font-weight: 500;
}
.match-detail {
  font-size: 12px;
  color: var(--cpq-text-muted);
  margin-left: 4px;
}
.match-error {
  background: var(--cpq-overlay-danger10);
  border-color: rgba(255, 107, 107, 0.25);
  color: var(--cpq-accent-danger);
}
.match-success {
  background: var(--cpq-overlay-a8);
  border-color: var(--cpq-overlay-a20);
  color: var(--cpq-accent-primary);
}
.match-warning {
  background: rgba(250, 173, 20, 0.1);
  border-color: rgba(250, 173, 20, 0.25);
  color: var(--cpq-color-warning);
}
</style>
