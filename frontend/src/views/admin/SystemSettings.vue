<template>
  <div class="system-settings">
    <div class="page-header">
      <h2>系统设置</h2>
      <p class="page-desc">全局配置，影响系统整体行为</p>
    </div>

    <div class="settings-section">
      <div class="settings-card">
        <div class="settings-card-title">数字精度</div>
        <p class="settings-card-desc">设置报价单中数字的显示精度，影响 Excel 导出和前端显示</p>
        <div class="setting-row">
          <span class="setting-label">小数位数：</span>
          <a-select
            v-model:value="numberPrecision"
            style="width: 120px"
            :loading="saving"
            @change="handlePrecisionChange"
          >
            <a-select-option :value="0">0 位</a-select-option>
            <a-select-option :value="2">2 位</a-select-option>
            <a-select-option :value="4">4 位</a-select-option>
          </a-select>
          <span class="setting-hint">当前：{{ numberPrecision }} 位小数</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

const numberPrecision = ref(2)
const saving = ref(false)

const loadPrecision = async () => {
  try {
    const res = await axios.get('/api/rules/number-precision')
    numberPrecision.value = res.data.precision
  } catch {
    message.error('加载精度设置失败')
  }
}

const handlePrecisionChange = async (value: number) => {
  saving.value = true
  try {
    await axios.put('/api/rules/number-precision', { precision: value })
    message.success('精度设置已保存')
  } catch {
    message.error('保存失败')
    await loadPrecision()
  } finally {
    saving.value = false
  }
}

onMounted(loadPrecision)
</script>

<style scoped>
.system-settings {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin: 0 0 8px 0;
}

.page-desc {
  font-size: 13px;
  color: var(--cpq-text-secondary);
  margin: 0;
}

.settings-section {
  max-width: 600px;
}

.settings-card {
  background: var(--cpq-bg-secondary);
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 8px;
  padding: 20px;
}

.settings-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 8px;
}

.settings-card-desc {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  margin: 0 0 16px 0;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.setting-label {
  font-size: 13px;
  color: var(--cpq-text-primary);
}

.setting-hint {
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
</style>
