<script setup lang="ts">
/**
 * 需求期望槽位清单编辑器（clarity_check 节点抽屉）—— 明确度判定数据源。
 * 编辑全局 system_config.requirement_slots：L0 底线（缺≥ask_threshold 反问）/
 * L1 重要（提示可补）/ L2 系统推导（不问）。key 固定（后端按 key 判定）。
 * 新增 per-field：required（是否必填）/ ask（是否反问）/ candidate_source（候选来源），
 * 需求理解节点与反问节点共用这份定义，避免硬编码。
 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

const LEVELS = [
  { value: 'L0', label: 'L0 底线（缺≥阈值反问）' },
  { value: 'L1', label: 'L1 重要（提示可补）' },
  { value: 'L2', label: 'L2 系统推导（不问）' },
]
const CANDIDATE_SOURCES = [
  { value: 'catalog', label: '目录白名单' },
  { value: 'free', label: '自由输入' },
]
// 旧清单/别名 key → 线索登记表规范 key（展示与保存统一，后端 slot_spec 亦走该映射）
const KEY_ALIAS_TO_CANONICAL: Record<string, string> = {
  scene: 'server_type', server_type: 'server_type', server_type_name: 'server_type',
  series: 'platform_type', platform_type: 'platform_type',
  form: 'chassis_form', chassis_form: 'chassis_form',
  model: 'server_model', server_model: 'server_model',
  drives: 'storage', storage: 'storage',
}
const CANONICAL_LABELS: Record<string, string> = {
  server_type: '服务器类型', platform_type: '平台/系列', chassis_form: '机箱形态',
  server_model: '机型', purchase_qty: '数量', warranty_years: '保修年限',
  cpu: 'CPU', memory: '内存', storage: '存储', gpu: 'GPU', nic: '网卡', raid: '阵列卡', psu: '电源',
}
const CATALOG_KEYS = new Set(['server_type', 'platform_type', 'chassis_form', 'server_model'])
const props = defineProps<{
  /** 内嵌到节点抽屉时用：隐藏独有工具栏说明，紧凑展示 */
  embedded?: boolean
  /** 只读预览：展示完整字段契约（含 KP 映射）但禁用编辑 */
  readonly?: boolean
  /** 反问节点聚焦：只展示「字段 / 反问 / 候选来源」，隐藏层级/必填/默认与排序增删 */
  askFocus?: boolean
  /** 隐藏 KP 大类映射（线索登记节点只保留字段 schema，不做映射旁路） */
  hideKpMap?: boolean
}>()
const slots = ref<Array<{ key: string; label: string; level: string; candidate_source: string }>>([])
const askThreshold = ref(2)
interface KpRow {
  category: string
  key: string
  candidate_source: string
}
const kpRows = ref<KpRow[]>([])
const kpLoading = ref(false)
const kpSaving = ref(false)
const PART_OPTIONS = [
  { value: 'cpu', label: 'CPU' },
  { value: 'memory', label: '内存' },
  { value: 'storage', label: '存储' },
  { value: 'gpu', label: 'GPU' },
  { value: 'nic', label: '网卡' },
  { value: 'raid', label: '阵列卡' },
  { value: 'psu', label: '电源' },
  { value: 'free', label: '不映射（自由行）' },
]
const loading = ref(false)
const saving = ref(false)

function typeHint(s: { key: string; candidate_source: string }): string {
  if (['purchase_qty', 'qty', 'warranty_years'].includes(s.key)) return '整数'
  return s.candidate_source === 'catalog' ? '枚举' : '文本'
}

function moveRow(idx: number, delta: number) {
  const next = idx + delta
  if (idx < 0 || next < 0 || next >= slots.value.length) return
  const list = slots.value
  const tmp = list[idx]
  list[idx] = list[next]
  list[next] = tmp
}

function removeRow(idx: number) {
  slots.value.splice(idx, 1)
}

function addRow() {
  slots.value.push({ key: '', label: '', level: 'L1', candidate_source: 'free' })
}

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/system-config/requirement_slots/value')
    const cfg = data.value || {}
    if (Array.isArray(cfg.slots) && cfg.slots.length) {
      slots.value = cfg.slots.map((s: any) => {
        const srcKey = s.key || ''
        const key = KEY_ALIAS_TO_CANONICAL[srcKey] || srcKey
        return {
          key, label: CANONICAL_LABELS[key] || s.label || key, level: s.level || 'L2',
          candidate_source: s.candidate_source || (CATALOG_KEYS.has(key) ? 'catalog' : 'free'),
        }
      })
      askThreshold.value = cfg.ask_threshold ?? 2
    } else {
      slots.value = []
      askThreshold.value = 2
      message.warning('字段配置为空，请在配置页先保存清单')
    }
  } catch (e) {
    console.error('加载槽位清单失败:', e)
    slots.value = []
    message.error('读取字段配置失败，请检查系统配置')
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

async function reset() {
  try {
    await axios.post('/api/system-config/requirement_slots/reset')
    await load()
    message.success('已恢复默认（来自系统配置种子）')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '恢复默认失败')
  }
}

async function loadKpMap() {
  kpLoading.value = true
  try {
    const [catRes, mapRes] = await Promise.all([
      axios.get('/api/kp/categories'),
      axios.get('/api/system-config/kp_slot_group_map/value'),
    ])
    const cats = (catRes.data || []) as Array<{ id: number; name: string }>
    const map: Record<string, any> = mapRes.data?.value || {}
    kpRows.value = cats.map((c) => {
      const name = String(c.name || '')
      const rule = (map && typeof map === 'object' ? map[name] : undefined) || {}
      const key = String(rule.key || 'free')
      return {
        category: name,
        key,
        candidate_source: String(rule.candidate_source || 'catalog'),
      }
    })
  } catch (e) {
    console.error('加载 KP 大类映射失败:', e)
    kpRows.value = []
  } finally {
    kpLoading.value = false
  }
}

async function saveKpMap() {
  kpSaving.value = true
  try {
    const map: Record<string, any> = {}
    for (const r of kpRows.value) {
      if (!r.key || r.key === 'free') continue
      map[r.category] = {
        key: r.key,
        candidate_source: r.candidate_source || 'catalog',
        group: '部件',
      }
    }
    await axios.put('/api/system-config/kp_slot_group_map', { value: map, type: 'json' })
    message.success('部件映射已保存（进度卡/反问题目即时生效）')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    kpSaving.value = false
  }
}

async function resetKpMap() {
  try {
    await axios.post('/api/system-config/kp_slot_group_map/reset')
    await loadKpMap()
    message.success('已恢复默认 KP 映射')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '恢复默认失败')
  }
}

onMounted(() => { load(); loadKpMap() })
</script>

<template>
  <div class="slot-editor">
    <a-alert v-if="!props.embedded" type="info" show-icon banner
      message="明确度 = 已填槽位 vs 期望清单差距：L0 缺 ≥ 阈值 → 反问；部件字段由 AI 填写，这里只维护 KP 大类到字段的映射" />
    <div class="slot-toolbar">
      <a-spin :spinning="loading" size="small" />
      <a-button v-if="!props.readonly" size="small" type="primary" :loading="saving" @click="save">保存清单</a-button>
      <a-button v-if="!props.embedded && !props.readonly" size="small" @click="reset">恢复默认</a-button>
    </div>
    <div class="slot-table">
    <div class="slot-row slot-head">
      <span class="slot-key">字段 key</span>
      <span class="slot-label">中文名 / 类型</span>
      <span v-if="!props.askFocus" class="slot-level">层级</span>
      <span class="slot-src">候选来源</span>
      <span v-if="!props.askFocus" class="slot-acts">顺序</span>
    </div>
    <div v-for="(s, i) in slots" :key="s.key || i" class="slot-row">
      <span class="slot-key">{{ s.key }}</span>
      <div class="slot-label">
        <a-input v-model:value="s.label" size="small" :placeholder="s.key" :disabled="props.readonly" />
        <span class="slot-type">{{ typeHint(s) }}</span>
      </div>
      <a-select v-if="!props.askFocus" v-model:value="s.level" size="small" class="slot-level" :options="LEVELS" :disabled="props.readonly" />
      <a-select v-model:value="s.candidate_source" size="small" class="slot-src" :options="CANDIDATE_SOURCES" :disabled="props.readonly" />
      <span v-if="!props.askFocus && !props.readonly" class="slot-acts">
        <a-button type="link" size="small" :disabled="i === 0" @click="moveRow(i, -1)">↑</a-button>
        <a-button type="link" size="small" :disabled="i === slots.length - 1" @click="moveRow(i, 1)">↓</a-button>
        <a-button type="link" danger size="small" @click="removeRow(i)">删</a-button>
      </span>
    </div>
    <div v-if="!props.askFocus && !props.readonly" class="slot-row slot-add">
      <a-button size="small" type="dashed" block @click="addRow">＋ 添加字段</a-button>
      <span class="slot-hint">字段清单从此处增删排序，不再写死在代码里</span>
    </div>
    </div>
        <a-collapse v-if="!props.askFocus && !props.hideKpMap" class="slot-kp-collapse" :bordered="false">
      <a-collapse-panel key="kp" header="部件字段映射（KP 大类 → 进度卡 / 反问题目）">
        <div class="slot-kp-toolbar">
          <a-spin :spinning="kpLoading" size="small" />
          <a-button v-if="!props.readonly" size="small" type="primary" :loading="kpSaving" @click="saveKpMap">保存映射</a-button>
          <a-button v-if="!props.readonly" size="small" @click="resetKpMap">恢复默认</a-button>
          <span class="slot-hint">「不映射（自由行）」的大类不进进度卡强制统计，由表单自由行承载</span>
        </div>
        <div class="slot-table slot-kp-table">
          <div class="slot-row slot-head">
            <span class="slot-key">KP 大类</span>
            <span class="slot-kp-map">映射字段</span>
            <span class="slot-src">候选来源</span>
          </div>
          <div v-for="r in kpRows" :key="r.category" class="slot-row" :class="{ 'slot-row-free': r.key === 'free' }">
            <span class="slot-key">{{ r.category }}</span>
            <a-select v-model:value="r.key" size="small" class="slot-kp-map" :options="PART_OPTIONS" :disabled="props.readonly || r.key === 'free'" />
            <a-select v-model:value="r.candidate_source" size="small" class="slot-src" :options="CANDIDATE_SOURCES" :disabled="props.readonly || r.key === 'free'" />
          </div>
          <div v-if="!kpRows.length" class="slot-hint" style="padding:6px 0">暂无可配置的 KP 大类。</div>
        </div>
      </a-collapse-panel>
    </a-collapse>
    <div class="slot-row slot-ask">
      <span class="slot-key">反问阈值</span>
      <a-input-number v-model:value="askThreshold" :min="1" :max="8" size="small" />
      <span class="slot-hint">L0 槽位缺 ≥ 此数 → 反问补全</span>
    </div>
    <p v-if="props.askFocus" class="slot-hint">是否反问由需求理解节点「字段配置」统一定义；此处仅配置候选来源。</p>
  </div>
</template>


<style scoped>
.slot-editor { display: flex; flex-direction: column; gap: 8px; }
.slot-table { overflow-x: auto; padding-bottom: 2px; }
.slot-table .slot-row { min-width: 840px; }
.slot-table .slot-row .slot-label { flex-shrink: 0; }
.slot-toolbar { display: flex; align-items: center; gap: 8px; }
.slot-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.slot-row.slot-head { color: var(--cpq-text-muted, #6E7582); }
.slot-key { width: 88px; flex-shrink: 0; }
.slot-label { width: 180px; display: flex; align-items: center; gap: 6px; }
.slot-type { font-size: 10px; color: var(--cpq-text-muted, #6E7582); white-space: nowrap; }
.slot-level { width: 190px; }
.slot-req { width: 48px; text-align: center; }
.slot-ask2 { width: 48px; text-align: center; }
.slot-src { width: 120px; }
.slot-ok { width: 90px; }
.slot-acts { display: inline-flex; align-items: center; gap: 2px; }
.slot-add { margin-top: 4px; align-items: flex-start; flex-direction: column; gap: 4px; }
.slot-kp-collapse { margin-top: 8px; }
.slot-kp-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; }
.slot-kp-table .slot-row { min-width: 1040px; }
.slot-kp-table .slot-key { width: 150px; }
.slot-kp-map { width: 140px; }
.slot-row-free { opacity: 0.6; }
.slot-ask { margin-top: 8px; }
.slot-hint { color: var(--cpq-text-muted, #6E7582); }
</style>
