<script setup lang="ts">
/**
 * 需求期望槽位清单编辑器（clarity_check 节点抽屉）—— 明确度判定数据源。
 * 编辑全局 system_config.requirement_slots：L0 底线（缺≥ask_threshold 反问）/
 * L1 重要（提示可补）/ L2 系统推导（不问）。key 固定（后端 _slot_filled 按 key 判定）。
 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

const LEVELS = [
  { value: 'L0', label: 'L0 底线（缺≥阈值反问）' },
  { value: 'L1', label: 'L1 重要（提示可补）' },
  { value: 'L2', label: 'L2 系统推导（不问）' },
]
const DEFAULT_SLOTS = [
  { key: 'scene', label: '应用场景', level: 'L0', default_ok: false },
  { key: 'series', label: '所属系列', level: 'L0', default_ok: false },
  { key: 'cpu', label: 'CPU', level: 'L0', default_ok: false },
  { key: 'memory', label: '内存', level: 'L0', default_ok: false },
  { key: 'storage', label: '存储', level: 'L0', default_ok: true },
  { key: 'form', label: '机箱形态', level: 'L1', default_ok: false },
  { key: 'gpu', label: 'GPU', level: 'L1', default_ok: false },
  { key: 'nic', label: '网卡', level: 'L1', default_ok: false },
  { key: 'raid', label: '阵列卡', level: 'L2', default_ok: false },
  { key: 'psu', label: '电源', level: 'L2', default_ok: false },
]

const slots = ref<Array<{ key: string; label: string; level: string; default_ok: boolean }>>([])
const askThreshold = ref(2)
const loading = ref(false)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/system-config/requirement_slots/value')
    const cfg = data.value || {}
    if (Array.isArray(cfg.slots) && cfg.slots.length) {
      slots.value = cfg.slots.map((s: any) => ({
        key: s.key || '', label: s.label || s.key || '', level: s.level || 'L2', default_ok: !!s.default_ok,
      }))
      askThreshold.value = cfg.ask_threshold ?? 2
    } else {
      slots.value = DEFAULT_SLOTS.map(s => ({ ...s }))
      askThreshold.value = 2
    }
  } catch (e) {
    console.error('加载槽位清单失败:', e)
    slots.value = DEFAULT_SLOTS.map(s => ({ ...s }))
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await axios.put('/api/system-config/requirement_slots', {
      value: { version: 1, ask_threshold: Number(askThreshold.value) || 2, slots: slots.value },
      type: 'json',
    })
    message.success('已保存（下次推理生效）')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function reset() {
  slots.value = DEFAULT_SLOTS.map(s => ({ ...s }))
  askThreshold.value = 2
  message.info('已恢复默认，请点击保存生效')
}

onMounted(load)
</script>

<template>
  <div class="slot-editor">
    <a-alert type="info" show-icon banner
      message="明确度 = 已填槽位 vs 期望清单差距：L0 缺 ≥ 阈值 → 反问；存储 default_ok（缺了给默认盘）；AI 场景缺 GPU 会反问" />
    <div class="slot-toolbar">
      <a-spin :spinning="loading" size="small" />
      <a-button size="small" type="primary" :loading="saving" @click="save">保存清单</a-button>
      <a-button size="small" @click="reset">恢复默认</a-button>
    </div>
    <div class="slot-row slot-head">
      <span class="slot-key">槽位</span>
      <span class="slot-label">显示名</span>
      <span class="slot-level">层级</span>
      <span class="slot-ok">缺了给默认</span>
    </div>
    <div v-for="s in slots" :key="s.key" class="slot-row">
      <span class="slot-key">{{ s.key }}</span>
      <a-input v-model:value="s.label" size="small" class="slot-label" />
      <a-select v-model:value="s.level" size="small" class="slot-level" :options="LEVELS" />
      <a-switch v-model:checked="s.default_ok" size="small" class="slot-ok" />
    </div>
    <div class="slot-row slot-ask">
      <span class="slot-key">反问阈值</span>
      <a-input-number v-model:value="askThreshold" :min="1" :max="8" size="small" />
      <span class="slot-hint">L0 槽位缺 ≥ 此数 → 反问补全</span>
    </div>
  </div>
</template>

<style scoped>
.slot-editor { display: flex; flex-direction: column; gap: 8px; }
.slot-toolbar { display: flex; align-items: center; gap: 8px; }
.slot-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.slot-row.slot-head { color: var(--cpq-text-muted, #6E7582); }
.slot-key { width: 72px; flex-shrink: 0; }
.slot-label { width: 150px; }
.slot-level { width: 200px; }
.slot-ok { width: 90px; }
.slot-ask { margin-top: 8px; }
.slot-hint { color: var(--cpq-text-muted, #6E7582); }
</style>
