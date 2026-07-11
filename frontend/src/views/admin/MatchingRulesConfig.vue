<template>
  <div class="matching-rules-config">
    <!-- 说明卡片 -->
    <a-card class="info-card" :bordered="false">
      <div class="info-content">
        <span class="info-icon">💡</span>
        <div>
          <div class="info-title">L6 匹配规则说明</div>
          <div class="info-desc">
            当系统解析报价单后，通过5个维度匹配L6历史价格。<br>
            <strong>匹配规则：</strong>PSU必须精确匹配，主板可降级（Polaris → Orion），机箱可模糊匹配（4U → 4.5U）。<br>
            <strong>匹配流程：</strong>精确匹配 → 主板降级 → 机箱模糊 → 报错
          </div>
        </div>
      </div>
    </a-card>

    <!-- 匹配维度优先级 -->
    <a-card title="📊 匹配维度优先级（拖拽调整顺序）" class="section-card">
      <draggable
        v-model="matchDimensions"
        item-key="key"
        class="dimension-list"
        ghost-class="ghost"
      >
        <template #item="{ element, index }">
          <div class="dimension-card">
            <div class="dimension-index">{{ index + 1 }}</div>
            <div class="dimension-info">
              <div class="dimension-label">{{ element.label }}</div>
              <div class="dimension-key">{{ element.key }}</div>
            </div>
            <div class="dimension-mode">{{ element.mode }}</div>
          </div>
        </template>
      </draggable>

      <div class="match-mode-config">
        <div class="mode-title">匹配模式配置：</div>
        <a-checkbox v-model:checked="allowMotherboardFallback">主板支持降级（Polaris → Orion）</a-checkbox>
        <a-checkbox v-model:checked="allowChassisFuzzy">机箱支持模糊匹配</a-checkbox>
      </div>
    </a-card>

    <!-- 机箱模糊匹配规则 -->
    <a-card title="📏 机箱模糊匹配规则" class="section-card" v-if="allowChassisFuzzy">
      <div class="fuzzy-rules-list">
        <div v-for="(rule, idx) in chassisFuzzyRules" :key="idx" class="fuzzy-rule-item">
          <span class="fuzzy-from">{{ rule.from }}</span>
          <span class="fuzzy-arrow">↔</span>
          <span class="fuzzy-to">{{ rule.to }}</span>
          <a-button type="text" danger size="small" @click="removeFuzzyRule(idx)">删除</a-button>
        </div>
      </div>
      <div class="add-fuzzy-rule">
        <a-input v-model:value="newFuzzyFrom" placeholder="如：4U" style="width: 100px" />
        <span>↔</span>
        <a-input v-model:value="newFuzzyTo" placeholder="如：4.5U" style="width: 100px" />
        <a-button type="primary" @click="addFuzzyRule">添加规则</a-button>
      </div>
    </a-card>

    <!-- 主板映射 -->
    <a-card title="🖥️ 主板映射" class="section-card">
      <MotherboardMapping ref="motherboardMappingRef" />
    </a-card>

    <!-- 保存按钮 -->
    <div class="action-bar">
      <a-button @click="reset">重置</a-button>
      <a-button type="primary" @click="save" :loading="saving">💾 保存</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import draggable from 'vuedraggable'
import MotherboardMapping from './MotherboardMapping.vue'

// 数据
const matchDimensions = ref([
  { key: 'psu', label: 'PSU', mode: '精确匹配' },
  { key: 'model', label: '机型', mode: '精确匹配' },
  { key: 'drive_bays', label: '盘位', mode: '精确匹配' },
  { key: 'motherboard', label: '主板', mode: '可降级' },
  { key: 'chassis', label: '机箱', mode: '可模糊' },
])

const allowMotherboardFallback = ref(true)
const allowChassisFuzzy = ref(true)

const chassisFuzzyRules = ref([
  { from: '2U', to: '2.5U' },
  { from: '4U', to: '4.5U' },
  { from: '1U', to: '2U' },
])

const newFuzzyFrom = ref('')
const newFuzzyTo = ref('')

const saving = ref(false)
const motherboardMappingRef = ref<InstanceType<typeof MotherboardMapping> | null>(null)

// 方法
const loadRules = async () => {
  try {
    const resp = await axios.get('/api/rules/matching-rules')
    const rules = resp.data.rules || []
    
    const dimsRule = rules.find((r: any) => r.rule_name === 'l6_match_dimensions')
    if (dimsRule) {
      const dims = JSON.parse(dimsRule.rule_value)
      matchDimensions.value = dims.map((key: string) => {
        const labelMap: Record<string, string> = {
          psu: 'PSU',
          model: '机型',
          drive_bays: '盘位',
          motherboard: '主板',
          chassis: '机箱',
        }
        const modeMap: Record<string, string> = {
          psu: '精确匹配',
          model: '精确匹配',
          drive_bays: '精确匹配',
          motherboard: '可降级',
          chassis: '可模糊',
        }
        return { key, label: labelMap[key] || key, mode: modeMap[key] || '精确匹配' }
      })
    }
    
    const mbFallbackRule = rules.find((r: any) => r.rule_name === 'allow_motherboard_fallback')
    if (mbFallbackRule) {
      allowMotherboardFallback.value = mbFallbackRule.rule_value === 'true'
    }
    
    const chassisFuzzyRule = rules.find((r: any) => r.rule_name === 'allow_chassis_fuzzy')
    if (chassisFuzzyRule) {
      allowChassisFuzzy.value = chassisFuzzyRule.rule_value === 'true'
    }
    
    const fuzzyRulesRule = rules.find((r: any) => r.rule_name === 'chassis_fuzzy_rules')
    if (fuzzyRulesRule) {
      chassisFuzzyRules.value = JSON.parse(fuzzyRulesRule.rule_value)
    }
  } catch (error) {
    console.error('Failed to load rules:', error)
  }
}

const addFuzzyRule = () => {
  if (!newFuzzyFrom.value || !newFuzzyTo.value) {
    message.warning('请填写完整的模糊匹配规则')
    return
  }
  chassisFuzzyRules.value.push({ from: newFuzzyFrom.value, to: newFuzzyTo.value })
  newFuzzyFrom.value = ''
  newFuzzyTo.value = ''
}

const removeFuzzyRule = (idx: number) => {
  chassisFuzzyRules.value.splice(idx, 1)
}

const reset = () => {
  // 重置匹配规则
  matchDimensions.value = [
    { key: 'psu', label: 'PSU', mode: '精确匹配' },
    { key: 'model', label: '机型', mode: '精确匹配' },
    { key: 'drive_bays', label: '盘位', mode: '精确匹配' },
    { key: 'motherboard', label: '主板', mode: '可降级' },
    { key: 'chassis', label: '机箱', mode: '可模糊' },
  ]
  allowMotherboardFallback.value = true
  allowChassisFuzzy.value = true
  chassisFuzzyRules.value = [
    { from: '2U', to: '2.5U' },
    { from: '4U', to: '4.5U' },
    { from: '1U', to: '2U' },
  ]
  // 重置主板映射
  motherboardMappingRef.value?.resetMappings()
  message.info('已重置为上次保存的状态')
}

const save = async () => {
  saving.value = true
  try {
    const rules = [
      {
        rule_name: 'l6_match_dimensions',
        rule_value: JSON.stringify(matchDimensions.value.map(d => d.key)),
        description: 'L6匹配维度优先级',
      },
      {
        rule_name: 'l6_fallback_dimensions',
        rule_value: JSON.stringify(['psu', 'model', 'drive_bays']),
        description: 'L6降级匹配维度',
      },
      {
        rule_name: 'allow_motherboard_fallback',
        rule_value: allowMotherboardFallback.value.toString(),
        description: '是否允许主板降级匹配',
      },
      {
        rule_name: 'allow_chassis_fuzzy',
        rule_value: allowChassisFuzzy.value.toString(),
        description: '是否允许机箱模糊匹配',
      },
      {
        rule_name: 'chassis_fuzzy_rules',
        rule_value: JSON.stringify(chassisFuzzyRules.value),
        description: '机箱模糊匹配规则',
      },
    ]
    
    // 并行保存匹配规则和主板映射
    await Promise.all([
      axios.put('/api/rules/matching-rules', rules),
      motherboardMappingRef.value?.saveMappings(),
    ])
    message.success('保存成功')
  } catch (error) {
    console.error('Failed to save rules:', error)
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadRules()
})
</script>

<style scoped>
.matching-rules-config {
  padding: 16px;
}

.info-card {
  margin-bottom: 16px;
  background: var(--ant-color-bg-container);
}

.info-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.info-icon {
  font-size: 24px;
}

.info-title {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 4px;
}

.info-desc {
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
}

.section-card {
  margin-bottom: 16px;
}

.dimension-list {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.dimension-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--ant-color-bg-layout);
  border-radius: 8px;
  cursor: move;
  transition: all 0.3s;
}

.dimension-card:hover {
  background: var(--ant-color-bg-container);
  box-shadow: 0 2px 8px var(--cpq-overlay-b15);
}

.ghost {
  opacity: 0.5;
  background: var(--ant-color-primary);
}

.dimension-index {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-primary);
  color: white;
  border-radius: 50%;
  font-weight: 600;
}

.dimension-info {
  flex: 1;
}

.dimension-label {
  font-weight: 600;
  font-size: 14px;
}

.dimension-key {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.dimension-mode {
  padding: 4px 8px;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  border-radius: 4px;
  font-size: 12px;
}

.match-mode-config {
  display: flex;
  gap: 16px;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border);
}

.mode-title {
  font-weight: 600;
}

.fuzzy-rules-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.fuzzy-rule-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--ant-color-bg-layout);
  border-radius: 6px;
}

.fuzzy-from, .fuzzy-to {
  font-weight: 600;
  padding: 4px 8px;
  background: var(--ant-color-bg-container);
  border-radius: 4px;
}

.fuzzy-arrow {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.add-fuzzy-rule {
  display: flex;
  gap: 8px;
  align-items: center;
}

.fallback-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fallback-step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--ant-color-bg-layout);
  border-radius: 6px;
}

.fallback-step.error {
  background: var(--ant-color-error-bg);
}

.step-number {
  font-weight: 600;
  color: var(--ant-color-primary);
  min-width: 60px;
}

.step-arrow {
  text-align: center;
  color: var(--ant-color-text-secondary);
  font-size: 18px;
}

.card-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.demo-filters {
  margin-bottom: 16px;
}

.filter-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.filter-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

:deep(.highlight-row) {
  background-color: var(--ant-color-primary-bg) !important;
}

:deep(.highlight-row td) {
  background-color: var(--ant-color-primary-bg) !important;
}

.match-result {
  margin-top: 16px;
}

.match-detail {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.manual-select {
  margin-top: 12px;
  padding: 12px;
  background: var(--ant-color-bg-layout);
  border-radius: 6px;
}

.select-item {
  padding: 8px 0;
}

.preview-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.preview-step {
  padding: 12px;
  background: var(--ant-color-bg-layout);
  border-radius: 6px;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.step-header.success {
  color: var(--ant-color-success);
}

.step-header.error {
  color: var(--ant-color-error);
}

.step-detail {
  font-weight: 600;
  margin-bottom: 4px;
}

.step-filter {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.action-bar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border);
}

/* 预览匹配弹窗样式 */
.preview-form {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--ant-color-bg-layout);
  border-radius: 6px;
}

.preview-result {
  margin-top: 16px;
}

.preview-step {
  padding: 16px;
  background: var(--ant-color-bg-layout);
  border-radius: 6px;
  margin-bottom: 12px;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.step-number {
  font-weight: 600;
  color: var(--ant-color-text);
}

.step-desc {
  flex: 1;
  color: var(--ant-color-text);
}

.step-badge {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
}

.step-header.success .step-badge {
  background: var(--ant-color-success-bg);
  color: var(--ant-color-success);
}

.step-header.error .step-badge {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
}

.step-candidates {
  margin-top: 12px;
  padding: 12px;
  background: var(--ant-color-bg-container);
  border-radius: 4px;
}

.candidate-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.candidate-item:last-child {
  border-bottom: none;
}

.cand-spec {
  color: var(--ant-color-text);
  font-size: 13px;
}

.cand-price {
  color: var(--ant-color-success);
  font-weight: 600;
}

.cand-more {
  text-align: center;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  margin-top: 8px;
}

.final-match {
  margin-top: 24px;
  padding: 20px;
  background: var(--ant-color-success-bg);
  border: 1px solid var(--ant-color-success-border);
  border-radius: 6px;
}

.final-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-success);
  margin-bottom: 12px;
}

.final-spec {
  color: var(--ant-color-text);
  margin-bottom: 8px;
}

.final-price {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-success);
}

.no-match {
  margin-top: 24px;
  padding: 20px;
  background: var(--ant-color-error-bg);
  border: 1px solid var(--ant-color-error-border);
  border-radius: 6px;
  text-align: center;
}

.no-match-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-error);
  margin-bottom: 8px;
}

.no-match-desc {
  color: var(--ant-color-text-secondary);
}
</style>
