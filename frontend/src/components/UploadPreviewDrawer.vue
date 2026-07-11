<template>
  <a-drawer
    :open="open"
    :width="900"
    title="报价单解析确认"
    :closable="true"
    :mask-closable="false"
    class="upload-preview-drawer"
    @close="handleClose"
  >
    <template #footer>
      <div class="drawer-footer">
        <a-button @click="handleClose">取消</a-button>
        <a-button type="primary" :loading="confirming" @click="handleConfirm">
          确认创建报价单
        </a-button>
      </div>
    </template>

    <div class="preview-content">
      <div v-if="loading" class="loading-state">
        <a-spin size="large" tip="正在解析报价单..." />
      </div>

      <template v-else-if="previewData">
        <!-- 多配置 Tab 切换 -->
        <div v-if="configKeys.length > 1" class="config-tabs">
          <div
            v-for="key in configKeys"
            :key="key"
            class="config-tab"
            :class="{ active: activeConfigKey === key }"
            @click="switchConfigTab(key)"
          >
            {{ key }}
          </div>
        </div>

        <!-- L6 整机匹配区域 -->
        <div class="section-title">
          <span class="title-icon">📦</span>
          L6 整机匹配
          <span v-if="configKeys.length > 1" class="config-badge">{{ activeConfigKey }}</span>
        </div>

        <div v-if="l6Meta" class="l6-meta-card glass">
          <div class="meta-grid">
            <div class="meta-item">
              <span class="meta-label">机箱</span>
              <span class="meta-value">{{ l6Meta.chassis_form || '—' }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">机型</span>
              <span class="meta-value">{{ l6Meta.l6_model_type || '—' }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">盘位</span>
              <span class="meta-value">{{ l6Meta.drive_bays || '—' }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">电源</span>
              <span class="meta-value">{{ l6Meta.psu || '—' }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">主板</span>
              <span class="meta-value">{{ l6Meta.motherboard || '—' }}</span>
            </div>
          </div>
        </div>

        <!-- L6 候选列表（Top 3） -->
        <div v-if="l6Candidates.length > 0" class="l6-candidates">
          <div
            v-for="(candidate, idx) in l6Candidates"
            :key="idx"
            class="candidate-card glass"
            :class="{ selected: selectedL6Index === idx }"
            @click="selectL6Candidate(idx)"
          >
            <div class="candidate-header">
              <span class="candidate-chassis">{{ candidate.chassis || '—' }}</span>
              <span class="candidate-score" :class="getScoreClass(candidate.match_score)">
                {{ candidate.match_score }}% 匹配
              </span>
            </div>
            <div class="candidate-specs">
              <span v-if="candidate.motherboard" class="spec-tag">主板: {{ candidate.motherboard }}</span>
              <span v-if="candidate.psu" class="spec-tag">电源: {{ candidate.psu }}</span>
              <span v-if="candidate.drive_bays" class="spec-tag">{{ candidate.drive_bays }}盘位</span>
            </div>
            <div class="candidate-footer">
              <span class="candidate-price">¥ {{ formatPrice(candidate.price) }}</span>
              <span v-if="candidate.update_date" class="candidate-date">{{ candidate.update_date }}</span>
            </div>
          </div>
        </div>

        <div v-else class="no-match-hint">
          <span class="hint-icon">⚠️</span>
          未找到匹配的 L6 记录，可稍后在报价单中手动选择
        </div>

        <!-- KP 配件列表 -->
        <div class="section-title">
          <span class="title-icon">🔧</span>
          KP 配件清单
          <span class="item-count">({{ kpItems.length }} 项)</span>
        </div>

        <div v-if="kpItems.length > 0" class="kp-list">
          <div v-for="(item, idx) in kpItems" :key="idx" class="kp-item glass">
            <div class="kp-info">
              <span class="kp-name">{{ item.part_name || item.name || '未命名' }}</span>
              <span class="kp-spec">{{ item.spec || '' }}</span>
            </div>
            <div class="kp-price-info">
              <span class="kp-qty">× {{ item.qty || 1 }}</span>
              <span v-if="item.db_price" class="kp-price">
                ¥ {{ formatPrice(item.db_price) }}
              </span>
              <span v-else class="kp-no-price">未匹配价格</span>
            </div>
          </div>
        </div>

        <div v-else class="no-kp-hint">
          <span class="hint-icon">📋</span>
          未解析到 KP 配件
        </div>
      </template>

      <div v-else-if="error" class="error-state">
        <span class="error-icon">❌</span>
        <p>{{ error }}</p>
      </div>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { parseQuotationPreview, confirmQuotationUpload, getL6Candidates } from '@/api/quote'

const props = defineProps<{
  open: boolean
  file: File | null
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'confirmed', data: { quotationId: string; previewData: any }): void
}>()

const loading = ref(false)
const confirming = ref(false)
const error = ref('')
const previewData = ref<any>(null)
const l6Candidates = ref<any[]>([])
const selectedL6Index = ref(0)

const configs = computed(() => previewData.value?.configs || {})
const configKeys = computed(() => Object.keys(configs.value))
const activeConfigKey = ref<string>('')

// 当 previewData 变化时，重置 activeConfigKey
watch(() => previewData.value, (newVal) => {
  if (newVal) {
    const keys = Object.keys(newVal.configs || {})
    activeConfigKey.value = keys.length > 0 ? keys[0] : ''
  }
}, { immediate: true })

const activeConfig = computed(() => {
  if (!activeConfigKey.value || !configs.value[activeConfigKey.value]) return null
  return configs.value[activeConfigKey.value]
})
const l6Meta = computed(() => activeConfig.value?.l6_meta || null)
const kpItems = computed(() => {
  if (!activeConfig.value) return []
  // 只显示 Key Parts 类别的项
  return (activeConfig.value.items || []).filter((item: any) => item.category === 'Key Parts')
})

const selectedL6Record = computed(() => {
  if (l6Candidates.value.length === 0) return null
  return l6Candidates.value[selectedL6Index.value] || null
})

function switchConfigTab(key: string) {
  activeConfigKey.value = key
  selectedL6Index.value = 0
  // 重新获取 L6 候选列表
  loadL6Candidates()
}

async function loadL6Candidates() {
  if (!l6Meta.value) return
  try {
    const candidates = await getL6Candidates({
      chassis: l6Meta.value.chassis_form,
      model: l6Meta.value.l6_model_type,
      drive_bays: l6Meta.value.drive_bays,
      psu: l6Meta.value.psu,
      motherboard: l6Meta.value.motherboard,
    })
    l6Candidates.value = candidates.candidates || []
  } catch (err) {
    console.error('Failed to load L6 candidates:', err)
  }
}

watch(() => props.open, async (newVal) => {
  if (newVal && props.file) {
    await loadPreview()
  } else if (!newVal) {
    resetState()
  }
})

async function loadPreview() {
  if (!props.file) return
  
  loading.value = true
  error.value = ''
  previewData.value = null
  l6Candidates.value = []
  selectedL6Index.value = 0
  
  try {
    const result = await parseQuotationPreview(props.file)
    previewData.value = result
    
    // 等待 activeConfigKey 被 watch 设置后，再获取 L6 候选
    await nextTick()
    await loadL6Candidates()
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || '解析失败'
    message.error(error.value)
  } finally {
    loading.value = false
  }
}

function selectL6Candidate(idx: number) {
  selectedL6Index.value = idx
}

function getScoreClass(score: number): string {
  if (score >= 80) return 'score-high'
  if (score >= 50) return 'score-medium'
  return 'score-low'
}

function formatPrice(price: number | string): string {
  const num = typeof price === 'string' ? parseFloat(price) : price
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function resetState() {
  previewData.value = null
  l6Candidates.value = []
  selectedL6Index.value = 0
  activeConfigKey.value = ''
  error.value = ''
}

function handleClose() {
  emit('update:open', false)
}

async function handleConfirm() {
  if (!props.file || !props.projectId) return
  
  confirming.value = true
  try {
    const result = await confirmQuotationUpload(props.file, props.projectId)
    
    // If user selected an L6 candidate, update the quotation
    if (selectedL6Record.value && result.quotation_id) {
      const { updateQuotationL6 } = await import('@/api/quote')
      await updateQuotationL6(result.quotation_id, selectedL6Record.value)
    }
    
    message.success('报价单创建成功')
    emit('confirmed', {
      quotationId: result.quotation_id,
      previewData: result
    })
    emit('update:open', false)
  } catch (err: any) {
    message.error(err.response?.data?.detail || err.message || '创建失败')
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
.upload-preview-drawer :deep(.ant-drawer-body) {
  padding: 0;
  background: var(--cpq-bg-primary, #0a0a0a);
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  background: var(--cpq-bg-secondary, #141414);
  border-top: 1px solid var(--border-color, var(--cpq-border-dark));
}

.preview-content {
  padding: 24px;
  min-height: 400px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: var(--cpq-accent-danger);
}

.error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary, var(--cpq-text-primary));
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color, var(--cpq-border-dark));
}

.title-icon {
  font-size: 20px;
}

.config-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--cpq-accent-primary, #00f5d4);
  background: var(--cpq-overlay-a10);
  border: 1px solid var(--cpq-overlay-a30);
  border-radius: 4px;
  padding: 2px 8px;
  margin-left: 8px;
}

.config-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color, var(--cpq-border-dark));
}

.config-tab {
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-secondary, #a0a0a0);
  background: var(--cpq-overlay-w3);
  border: 1px solid var(--cpq-overlay-w8);
  cursor: pointer;
  transition: all 0.2s var(--cpq-ease-out-expo, ease);
}

.config-tab:hover {
  color: var(--cpq-text-primary, var(--cpq-text-primary));
  border-color: var(--cpq-overlay-a30);
}

.config-tab.active {
  color: var(--cpq-accent-primary, #00f5d4);
  background: var(--cpq-overlay-a8);
  border-color: var(--cpq-overlay-a40);
}

.item-count {
  font-size: 14px;
  font-weight: normal;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.glass {
  background: var(--cpq-overlay-w3);
  backdrop-filter: blur(10px);
  border: 1px solid var(--cpq-overlay-w8);
  border-radius: 12px;
}

.l6-meta-card {
  padding: 16px;
  margin-bottom: 16px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-label {
  font-size: 12px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.meta-value {
  font-size: 14px;
  color: var(--cpq-text-primary, var(--cpq-text-primary));
  font-weight: 500;
}

.l6-candidates {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}

.candidate-card {
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.candidate-card:hover {
  border-color: var(--cpq-accent-primary, var(--cpq-color-info));
  transform: translateY(-2px);
}

.candidate-card.selected {
  border-color: var(--cpq-accent-primary, var(--cpq-color-info));
  background: rgba(24, 144, 255, 0.08);
  box-shadow: 0 0 0 2px var(--cpq-overlay-info20);
}

.candidate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.candidate-chassis {
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary, var(--cpq-text-primary));
}

.candidate-score {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.candidate-score.score-high {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}

.candidate-score.score-medium {
  background: var(--cpq-overlay-warn30);
  color: var(--cpq-color-warning);
}

.candidate-score.score-low {
  background: var(--cpq-overlay-danger15);
  color: var(--cpq-accent-danger);
}

.candidate-specs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.spec-tag {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--cpq-overlay-w6);
  border-radius: 4px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.candidate-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--cpq-overlay-w6);
}

.candidate-price {
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-accent-primary, var(--cpq-color-info));
}

.candidate-date {
  font-size: 12px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.no-match-hint, .no-kp-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: rgba(250, 173, 20, 0.05);
  border: 1px solid rgba(250, 173, 20, 0.2);
  border-radius: 8px;
  color: var(--cpq-text-secondary, #a0a0a0);
  margin-bottom: 24px;
}

.hint-icon {
  font-size: 20px;
}

.kp-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kp-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
}

.kp-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.kp-name {
  font-size: 14px;
  color: var(--cpq-text-primary, var(--cpq-text-primary));
  font-weight: 500;
}

.kp-spec {
  font-size: 12px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.kp-price-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kp-qty {
  font-size: 13px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.kp-price {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-accent-primary, var(--cpq-color-info));
}

.kp-no-price {
  font-size: 12px;
  color: var(--cpq-text-secondary, #a0a0a0);
  font-style: italic;
}
</style>
