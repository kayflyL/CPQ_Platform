<script setup lang="ts">
/** 基准配置组装（管理面）— 从料号库挑底盘件（含背板），组新机箱方案。对应原型管理面基准配置。 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { baseConfigApi, partsApi, bomTemplateApi, type BaseConfig, type BomTemplate, type PartMaster } from '@/api/serverConfig'
import PartPicker from '@/components/common/PartPicker.vue'
import { fromPartMaster } from '@/composables/usePartAdapter'

const configs = ref<BaseConfig[]>([])
const templates = ref<BomTemplate[]>([])
const loading = ref(false)
const modalVisible = ref(false)
const saving = ref(false)
const form = ref<any>({})
const commonLines = ref<{ cat: string; pn: string; qty: number }[]>([])
const allParts = ref<PartMaster[]>([])
const editingId = ref<number | null>(null)

async function load() {
  loading.value = true
  try {
    const [cfgRes, tplRes] = await Promise.all([baseConfigApi.list(), bomTemplateApi.list()])
    configs.value = cfgRes.configs
    templates.value = tplRes.templates || []
  } finally { loading.value = false }
}
const chassisCats = ref<string[]>([])
const ALL_CAT = '全部'
function partsOf(cat: string) { return cat === ALL_CAT ? allParts.value : allParts.value.filter(p => p.category === cat) }
function partByPn(pn?: string) { return allParts.value.find(p => p.pn === pn) }

async function openNew() {
  editingId.value = null
  form.value = { name: '', series: 'Orion', form: '2U', bays: 12, bom_template_id: null }
  commonLines.value = []
  modalVisible.value = true
  if (!allParts.value.length) {
    const [partsRes, catsRes] = await Promise.all([partsApi.list(), partsApi.categories()])
    allParts.value = partsRes.parts
    chassisCats.value = catsRes.categories
  }
}
async function openEdit(b: any) {
  editingId.value = b.id
  const full = await baseConfigApi.get(b.id)
  form.value = { name: full.name, series: full.series, form: full.form, bays: full.bays, bom_template_id: full.bom_template_id ?? null }
  commonLines.value = (full.parts || []).map((p: any) => ({ cat: p.category, pn: p.pn, qty: p.quantity }))
  modalVisible.value = true
  if (!allParts.value.length) {
    const [partsRes, catsRes] = await Promise.all([partsApi.list(), partsApi.categories()])
    allParts.value = partsRes.parts
    chassisCats.value = catsRes.categories
  }
}
function addLine() { commonLines.value.push({ cat: ALL_CAT, pn: '', qty: 1 }) }
function delLine(i: number) { commonLines.value.splice(i, 1) }
function moveLine(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= commonLines.value.length) return
  const arr = commonLines.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}
function onCatChange(i: number) {
  // 切到具体类别时，若当前料不在该类别则清空（让用户在该类别内重选）；切到"全部"则保留
  const l = commonLines.value[i]
  if (l.cat !== ALL_CAT && l.pn && !partsOf(l.cat).some(p => p.pn === l.pn)) l.pn = ''
}
// 选中料后自动回填该料的真实类别（行能体现自己是什么件，类别选择器仍可随时切回"全部"再搜）
function onPartPick(i: number, pn: string) {
  const l = commonLines.value[i]
  l.pn = pn
  const p = partByPn(pn)
  if (p) l.cat = p.category
}

async function save() {
  if (!form.value.name) return message.warning('请填基准名称')
  const parts = commonLines.value.filter(l => l.pn)
  if (!parts.length) return message.warning('请至少添加一个底盘件')
  saving.value = true
  try {
    const payload: any = {
      name: form.value.name, series: form.value.series, model: form.value.name,
      form: form.value.form, bays: form.value.bays, gpu_arch_default: 'none',
      bom_template_id: form.value.bom_template_id ?? null,
    }
    let id = editingId.value
    if (id) await baseConfigApi.update(id, payload)
    else id = (await baseConfigApi.create(payload)).id
    await baseConfigApi.setParts(id!, commonLines.value.filter(l => l.pn).map((l, idx) => ({ pn: l.pn, quantity: l.qty, sort_order: idx })))
    message.success((editingId.value ? '已更新' : '已新建') + '基准配置「' + form.value.name + '」')
    modalVisible.value = false
    load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}
async function remove(id: number, name: string) {
  await baseConfigApi.delete(id); message.success('已删除 ' + name); load()
}
const columns = [
  { title: '基准名称', dataIndex: 'name', key: 'name' },
  { title: '系列', dataIndex: 'series', key: 'series', width: 90 },
  { title: '形态', dataIndex: 'form', key: 'form', width: 70 },
  { title: '盘位', dataIndex: 'bays', key: 'bays', width: 70 },
  { title: '料件数', dataIndex: 'parts_count', key: 'parts_count', width: 80 },
  { title: '合计', dataIndex: 'total_price', key: 'total_price', width: 110 },
  { title: '操作', key: 'op', width: 80 },
]
onMounted(load)
</script>

<template>
  <div class="panel glass">
    <div class="lib-head">
      <h3>基准配置</h3>
      <a-button type="primary" size="small" @click="openNew">+ 新建基准配置（挑件组装）</a-button>
    </div>
    <a-table :data-source="configs" :columns="columns" :loading="loading" row-key="id" size="small" :pagination="false">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'parts_count'">
          <span class="cell-num">{{ record.parts_count ?? 0 }}</span>
        </template>
        <template v-else-if="column.key === 'total_price'">
          <span class="cell-price">¥{{ (record.total_price ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
        </template>
        <template v-else-if="column.key === 'op'">
          <a-button size="small" link @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="删除该基准配置？" @confirm="remove(record.id, record.name)">
            <a-button size="small" link danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <a-modal :open="modalVisible" :title="editingId ? '编辑基准配置' : '新建基准配置（自己挑件组机箱）'" width="880px" :okText="saving ? '保存中…' : '保存'"
             @ok="save" @cancel="modalVisible = false" :destroyOnClose="true">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="10"><a-form-item label="基准名称" required><a-input v-model:value="form.name" /></a-form-item></a-col>
          <a-col :span="5"><a-form-item label="系列"><a-select v-model:value="form.series"><a-select-option value="Orion">Orion·AMD</a-select-option><a-select-option value="Polaris">Polaris·兆芯</a-select-option></a-select></a-form-item></a-col>
          <a-col :span="4"><a-form-item label="形态"><a-select v-model:value="form.form"><a-select-option value="2U">2U</a-select-option><a-select-option value="4U">4U</a-select-option></a-select></a-form-item></a-col>
          <a-col :span="5"><a-form-item label="盘位"><a-input-number v-model:value="form.bays" :min="1" style="width:100%" /></a-form-item></a-col>
        </a-row>

        <div class="sec-label">底盘件（在选料器里直接搜索料号 / 名称 / PN，可跨类别；选中后自动归类）</div>
        <div v-for="(l, i) in commonLines" :key="i" class="line-block">
          <div class="line-row">
            <div class="line-move">
              <span class="line-idx">{{ i + 1 }}</span>
              <button class="move-btn" :disabled="i === 0" title="上移" @click="moveLine(i, -1)">↑</button>
              <button class="move-btn" :disabled="i === commonLines.length - 1" title="下移" @click="moveLine(i, 1)">↓</button>
            </div>
            <a-select v-model:value="l.cat" style="width:140px" @change="onCatChange(i)">
              <a-select-option :value="ALL_CAT">🔍 全部类别</a-select-option>
              <a-select-option v-for="c in chassisCats" :key="c" :value="c">{{ c }}</a-select-option>
            </a-select>
            <PartPicker style="flex:1" :items="partsOf(l.cat).map(fromPartMaster)" :model-value="l.pn"
                        placeholder="🔍 搜索料号 / 名称 / PN…"
                        @update:model-value="(pn:any)=>onPartPick(i, typeof pn==='string'?pn:'')">
              <template #option="{ item }">
                <div class="bcb-opt">
                  <div class="bcb-opt-row">
                    <span class="bcb-opt-name">{{ item.name }}</span>
                    <span v-if="item.unit_price != null" class="bcb-opt-price">¥{{ item.unit_price.toLocaleString() }}</span>
                  </div>
                  <div class="bcb-opt-sub">
                    <span class="bcb-opt-cat">{{ item.category }}</span>
                    <span class="bcb-opt-pn">{{ item.pn }}</span>
                  </div>
                </div>
              </template>
            </PartPicker>
            <a-input-number v-model:value="l.qty" :min="1" style="width:80px" />
            <a-button danger @click="delLine(i)">✕</a-button>
          </div>
          <div class="line-info" v-if="partByPn(l.pn)">
            <span class="li-desc">{{ partByPn(l.pn)?.description || '（无描述）' }}</span>
            <span class="li-price">¥{{ (partByPn(l.pn)?.unit_price ?? 0).toLocaleString() }}</span>
          </div>
        </div>
        <a-button dashed style="margin-top:6px" @click="addLine">+ 添加底盘件</a-button>

        <!-- BOM 模板（在下方「BOM 模板」卡片管理，这里只选关联哪个）-->
        <a-form-item label="BOM 模板">
          <a-select v-model:value="form.bom_template_id" allow-clear placeholder="(无模板 — 左栏回落原始行)">
            <a-select-option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}（{{ t.rows?.length || 0 }}行）</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.sec-label { font-size: 13px; color: var(--cpq-text-muted, #6E7582); margin-bottom: 8px; }
.line-block { margin-bottom: 12px; }
.line-row { display: flex; gap: 8px; align-items: center; }
.line-move { display: flex; flex-direction: column; align-items: center; gap: 1px; flex-shrink: 0; }
.line-idx { font-size: 11px; color: var(--cpq-text-muted, #6E7582); font-variant-numeric: tabular-nums; line-height: 1; margin-bottom: 1px; }
.move-btn { width: 20px; height: 14px; border: 1px solid var(--cpq-overlay-w10, #d9d9d9); background: transparent; color: var(--cpq-text-secondary, #9BA1AA); font-size: 10px; line-height: 1; cursor: pointer; border-radius: 3px; padding: 0; transition: all .15s; }
.move-btn:hover:not(:disabled) { color: var(--cpq-accent-primary, #1677FF); border-color: var(--cpq-accent-primary, #1677FF); }
.move-btn:disabled { opacity: .35; cursor: not-allowed; }
.line-info { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; padding: 4px 4px 0; margin-top: 2px; font-size: 14px; line-height: 1.5; }
.line-info .li-desc { color: var(--cpq-text-secondary, #9BA1AA); min-width: 0; }
.line-info .li-price { color: var(--cpq-accent-primary, #1677FF); font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.cell-num { font-variant-numeric: tabular-nums; color: var(--cpq-text-secondary, #9BA1AA); }
.cell-price { font-weight: 700; color: var(--cpq-accent-primary, #1677FF); font-variant-numeric: tabular-nums; }
</style>

<!-- PartPicker 下拉 teleported 到 body，非 scoped；用 .bcb-opt 前缀限定 -->
<style>
.bcb-opt { padding: 5px 2px; line-height: 1.45; }
.bcb-opt-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.bcb-opt-name { font-size: 14px; color: var(--cpq-text-primary, #E8ECEF); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bcb-opt-price { font-size: 13px; color: var(--cpq-accent-primary, #1677FF); font-weight: 600; white-space: nowrap; }
.bcb-opt-sub { display: flex; gap: 8px; align-items: center; margin-top: 2px; font-size: 12px; }
.bcb-opt-cat { color: var(--cpq-accent-primary, #1677FF); }
.bcb-opt-pn { color: var(--cpq-text-muted, #6E7582); margin-left: auto; font-family: monospace; }
</style>
