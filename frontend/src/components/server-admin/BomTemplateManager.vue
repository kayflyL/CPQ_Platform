<script setup lang="ts">
/** BOM 模板管理（管理面独立卡片，挂在基准配置列表下方）— 列表 + 编辑弹窗。
 *  每模板 = 行骨架(type/label/slot/mode) + 每行 rule(desc/qty 怎么算)。
 *  规则跟模板存 JSONB、求值跑前端；基准配置通过 bom_template_id 关联此处的模板。 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { bomTemplateApi, type BomTemplate, type BomTemplateRow } from '@/api/serverConfig'
import BomRuleSourceEditor from './BomRuleSourceEditor.vue'

const templates = ref<(BomTemplate & { _usage?: number })[]>([])
const loading = ref(false)
const modalVisible = ref(false)
const editingId = ref<number | null>(null)
const name = ref('')
const rows = ref<BomTemplateRow[]>([])
const saving = ref(false)

const ROW_TYPES = [
  { value: 'front_backplane', label: 'Front backplane（前面背板）' },
  { value: 'io_slot', label: 'IO 槽位（IO1~IO4）' },
  { value: 'rear_summary', label: '后面板汇总（Direct/Switch）' },
  { value: 'heatsink', label: 'Heatsink（散热器）' },
  { value: 'fan', label: 'FAN（风扇）' },
  { value: 'psu_requirement', label: 'Power Supply Requirement（电源需求）' },
  { value: 'gpu_power_cord', label: 'GPU Power cord（GPU 电源线）' },
  { value: 'power_cord', label: 'Power cord（电源线）' },
  { value: 'rail_kit', label: 'Rail kit（滑轨）' },
  { value: 'cable', label: 'Cable（线缆）' },
  { value: 'raid_slot', label: 'Raid slot（Switch 机型）' },
]
const SLOT_OPTIONS = ['IO1', 'IO2', 'IO3', 'IO4']

// ---- 行规则编辑(primary + 可选 fallback)----
const expanded = ref<Set<number>>(new Set())
function toggleRule(i: number) {
  ensureRule(rows.value[i])
  const s = new Set(expanded.value); s.has(i) ? s.delete(i) : s.add(i); expanded.value = s
}
function ensureRule(r: BomTemplateRow) {
  if (!r.rule) r.rule = { desc: { kind: 'manual' }, qty: { kind: 'manual' } }
}
function onDescChange(r: BomTemplateRow, v: any) { ensureRule(r); r.rule!.desc = v }
function onQtyChange(r: BomTemplateRow, v: any) { ensureRule(r); r.rule!.qty = v }
function toggleDescFb(r: BomTemplateRow, on: boolean) {
  ensureRule(r); r.rule!.desc_fallback = on ? { kind: 'manual' } : undefined
}
function toggleQtyFb(r: BomTemplateRow, on: boolean) {
  ensureRule(r); r.rule!.qty_fallback = on ? { kind: 'manual' } : undefined
}
function canFallback(kind: string) { return kind !== 'manual' && kind !== 'fixed' }

function addRow() { rows.value.push({ type: 'cable', label: 'Cable' }) }
function delRow(i: number) { rows.value.splice(i, 1) }
function move(i: number, d: number) {
  const j = i + d
  if (j < 0 || j >= rows.value.length) return
  const arr = rows.value; const t = arr[i]; arr[i] = arr[j]; arr[j] = t
}
function onTypeChange(i: number) {
  const r = rows.value[i]
  if (r.type === 'io_slot') { if (!r.slot) r.slot = 'IO1' } else { delete r.slot }
  if (r.type === 'rear_summary') { if (!r.mode) r.mode = 'direct' } else { delete r.mode }
  const def = ROW_TYPES.find(t => t.value === r.type)
  if (def && !r.label) r.label = def.label.split('（')[0]
}

async function load() {
  loading.value = true
  try {
    const r = await bomTemplateApi.list()
    const list = r.templates || []
    const usages = await Promise.all(list.map(t =>
      fetch(`/api/bom-templates/${t.id}/usage`).then(x => x.json()).catch(() => ({ count: 0 })))
    )
    templates.value = list.map((t, i) => ({ ...t, _usage: usages[i]?.count || 0 }))
  } finally { loading.value = false }
}
function openNew() {
  editingId.value = null; name.value = ''; rows.value = []; expanded.value = new Set(); modalVisible.value = true
}
async function openEdit(t: BomTemplate) {
  editingId.value = t.id
  const full = await bomTemplateApi.get(t.id)
  name.value = full.name
  rows.value = (full.rows || []).map(r => ({ ...r }))
  expanded.value = new Set()
  modalVisible.value = true
}
async function save() {
  if (!name.value.trim()) return message.warning('请填模板名')
  for (const r of rows.value) {
    if (r.type === 'io_slot' && !r.slot) return message.warning('IO 槽位行需选 slot（IO1~IO4）')
  }
  saving.value = true
  try {
    const payload = { name: name.value.trim(), rows: rows.value }
    if (editingId.value) await bomTemplateApi.update(editingId.value, payload)
    else editingId.value = (await bomTemplateApi.create(payload)).id
    message.success('模板已保存（所有用此模板的基准配置立即生效）')
    modalVisible.value = false
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}
async function remove(t: BomTemplate) {
  try {
    const r = await bomTemplateApi.delete(t.id)
    message.success(`已删除${r.detached_base_configs ? `（${r.detached_base_configs} 个基准配置被解绑）` : ''}`)
    await load()
  } catch { message.error('删除失败') }
}

const columns = [
  { title: '模板名', dataIndex: 'name', key: 'name' },
  { title: '行数', key: 'rows', width: 80 },
  { title: '用途', key: 'usage', width: 100 },
  { title: '操作', key: 'op', width: 120 },
]
onMounted(load)
defineExpose({ load })
</script>

<template>
  <div class="panel glass">
    <div class="lib-head">
      <h3>BOM 模板</h3>
      <a-button type="primary" size="small" @click="openNew">+ 新建模板</a-button>
    </div>
    <div class="tpl-hint">左栏 L6 配置单的机型族行骨架 + 每行解析规则(desc/qty 怎么算)。基准配置通过下拉关联此处的模板。</div>
    <a-table :data-source="templates" :columns="columns" :loading="loading" row-key="id" size="small" :pagination="false">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'rows'">{{ record.rows?.length || 0 }} 行</template>
        <template v-else-if="column.key === 'usage'">{{ record._usage ?? 0 }} 个基准</template>
        <template v-else-if="column.key === 'op'">
          <a-button size="small" link @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="删除该模板？关联的基准配置会变为无模板。" @confirm="remove(record)">
            <a-button size="small" link danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <a-modal :open="modalVisible" :title="editingId ? '编辑 BOM 模板' : '新建 BOM 模板'" width="800px"
             :okText="saving ? '保存中…' : '保存'" @ok="save" @cancel="modalVisible = false" :destroyOnClose="true">
      <a-form layout="vertical">
        <a-form-item label="模板名" required>
          <a-input v-model:value="name" placeholder="如：2U12标准、4U8-GPU直连" />
        </a-form-item>
        <div class="sec-label">行骨架（顺序即左栏显示顺序）· 点 ⚙ 配置该行 desc/qty 的解析规则</div>
        <div class="row-list">
          <div v-for="(r, i) in rows" :key="i" class="tpl-row-wrap">
            <div class="tpl-row">
              <span class="row-idx">{{ i + 1 }}</span>
              <a-select :value="r.type" size="small" style="width: 200px" @change="(v: string) => { r.type = v; onTypeChange(i) }">
                <a-select-option v-for="t in ROW_TYPES" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
              </a-select>
              <a-input v-model:value="r.label" size="small" style="flex:1" placeholder="左栏显示的标签（如 Front backplane）" />
              <a-select v-if="r.type === 'io_slot'" v-model:value="r.slot" size="small" style="width: 80px">
                <a-select-option v-for="s in SLOT_OPTIONS" :key="s" :value="s">{{ s }}</a-select-option>
              </a-select>
              <a-select v-else-if="r.type === 'rear_summary'" v-model:value="r.mode" size="small" style="width: 100px">
                <a-select-option value="direct">direct</a-select-option>
                <a-select-option value="switch">switch</a-select-option>
              </a-select>
              <div class="row-move">
                <a-button size="small" link :disabled="i === 0" @click="move(i, -1)">↑</a-button>
                <a-button size="small" link :disabled="i === rows.length - 1" @click="move(i, 1)">↓</a-button>
              </div>
              <a-button size="small" link :class="{ 'rule-active': expanded.has(i) }" @click="toggleRule(i)" title="解析规则">⚙</a-button>
              <a-button size="small" link danger @click="delRow(i)">✕</a-button>
            </div>
            <div v-if="expanded.has(i) && r.rule" class="tpl-rule">
              <div class="rule-line">
                <span class="rule-lab">Description</span>
                <BomRuleSourceEditor :model-value="r.rule.desc" mode="desc" @update:model-value="(v: any) => onDescChange(r, v)" />
              </div>
              <div class="rule-line" v-if="canFallback(r.rule.desc.kind)">
                <span class="rule-lab sub">└ 兜底</span>
                <a-checkbox :checked="!!r.rule.desc_fallback" @change="(e: any) => toggleDescFb(r, e.target.checked)">算不出时启用</a-checkbox>
                <BomRuleSourceEditor v-if="r.rule.desc_fallback" :model-value="r.rule.desc_fallback" mode="desc"
                  @update:model-value="(v: any) => { r.rule!.desc_fallback = v }" />
              </div>
              <div class="rule-line">
                <span class="rule-lab">Quantity</span>
                <BomRuleSourceEditor :model-value="r.rule.qty" mode="qty" @update:model-value="(v: any) => onQtyChange(r, v)" />
              </div>
              <div class="rule-line" v-if="canFallback(r.rule.qty.kind)">
                <span class="rule-lab sub">└ 兜底</span>
                <a-checkbox :checked="!!r.rule.qty_fallback" @change="(e: any) => toggleQtyFb(r, e.target.checked)">算不出时启用</a-checkbox>
                <BomRuleSourceEditor v-if="r.rule.qty_fallback" :model-value="r.rule.qty_fallback" mode="qty"
                  @update:model-value="(v: any) => { r.rule!.qty_fallback = v }" />
              </div>
            </div>
          </div>
        </div>
        <a-button size="small" dashed style="margin-top:6px" @click="addRow">+ 添加行</a-button>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.tpl-hint { font-size: 11px; color: var(--cpq-text-muted, #6E7582); margin-bottom: 10px; line-height: 1.5; }
.sec-label { font-size: 12px; color: var(--cpq-text-muted, #6E7582); margin-bottom: 8px; }
.row-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
.tpl-row-wrap { display: flex; flex-direction: column; gap: 4px; }
.tpl-row { display: flex; align-items: center; gap: 6px; }
.row-idx { width: 18px; font-size: 11px; color: var(--cpq-text-muted, #6E7582); text-align: right; }
.row-move { display: flex; flex-direction: column; }
.rule-active { color: var(--cpq-accent-primary, #1677FF); }
.tpl-rule { padding: 6px 8px 6px 24px; background: var(--cpq-overlay-w3); border-radius: 6px; display: flex; flex-direction: column; gap: 4px; }
.rule-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rule-lab { font-size: 11px; color: var(--cpq-text-muted, #6E7582); width: 80px; flex-shrink: 0; }
.rule-lab.sub { padding-left: 8px; }
</style>
