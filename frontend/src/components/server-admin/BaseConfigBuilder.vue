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
function partsOf(cat: string) { return allParts.value.filter(p => p.category === cat) }
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
function addLine() { commonLines.value.push({ cat: '机箱', pn: (partsOf('机箱')[0] || {}).pn || '', qty: 1 }) }
function delLine(i: number) { commonLines.value.splice(i, 1) }
function onCatChange(i: number) { commonLines.value[i].pn = (partsOf(commonLines.value[i].cat)[0] || {}).pn || '' }

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
    await baseConfigApi.setParts(id!, parts.map(l => ({ pn: l.pn, quantity: l.qty })))
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
  { title: '操作', key: 'op', width: 80 },
]
onMounted(load)
</script>

<template>
  <div class="panel">
    <div class="lib-head">
      <h3>基准配置</h3>
      <a-button type="primary" size="small" @click="openNew">+ 新建基准配置（挑件组装）</a-button>
    </div>
    <a-table :data-source="configs" :columns="columns" :loading="loading" row-key="id" size="small" :pagination="false">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'op'">
          <a-button size="small" link @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="删除该基准配置？" @confirm="remove(record.id, record.name)">
            <a-button size="small" link danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <a-modal :open="modalVisible" :title="editingId ? '编辑基准配置' : '新建基准配置（自己挑件组机箱）'" width="780px" :okText="saving ? '保存中…' : '保存'"
             @ok="save" @cancel="modalVisible = false" :destroyOnClose="true">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="10"><a-form-item label="基准名称" required><a-input v-model:value="form.name" /></a-form-item></a-col>
          <a-col :span="5"><a-form-item label="系列"><a-select v-model:value="form.series"><a-select-option value="Orion">Orion·AMD</a-select-option><a-select-option value="Polaris">Polaris·兆芯</a-select-option></a-select></a-form-item></a-col>
          <a-col :span="4"><a-form-item label="形态"><a-select v-model:value="form.form"><a-select-option value="2U">2U</a-select-option><a-select-option value="4U">4U</a-select-option></a-select></a-form-item></a-col>
          <a-col :span="5"><a-form-item label="盘位"><a-input-number v-model:value="form.bays" :min="1" style="width:100%" /></a-form-item></a-col>
        </a-row>

        <div class="sec-label">底盘件（从 L6 料号库选件组装，料跨机型共用）</div>
        <div v-for="(l, i) in commonLines" :key="i" class="line-block">
          <div class="line-row">
            <a-select v-model:value="l.cat" style="width:130px" size="small" @change="onCatChange(i)">
              <a-select-option v-for="c in chassisCats" :key="c" :value="c">{{ c }}</a-select-option>
            </a-select>
            <PartPicker style="flex:1" :items="partsOf(l.cat).map(fromPartMaster)" :model-value="l.pn" size="small" placeholder="(选择料号)" @update:model-value="(pn:any)=>{ l.pn = typeof pn === 'string' ? pn : '' }" />
            <a-input-number v-model:value="l.qty" :min="1" style="width:70px" size="small" />
            <a-button size="small" danger @click="delLine(i)">✕</a-button>
          </div>
          <div class="line-info">{{ partByPn(l.pn)?.description || '无描述' }} · ¥{{ partByPn(l.pn)?.unit_price ?? 0 }}</div>
        </div>
        <a-button size="small" dashed style="margin-top:6px" @click="addLine">+ 添加底盘件</a-button>

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
.panel { background: var(--cpq-bg-card, #14161c); border: 1px solid var(--cpq-border-primary, rgba(255,255,255,.10)); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.sec-label { font-size: 12px; color: var(--cpq-text-muted, #6E7582); margin-bottom: 6px; }
.line-block { margin-bottom: 10px; }
.line-row { display: flex; gap: 8px; align-items: center; }
.line-info { font-size: 12px; color: var(--cpq-text-muted, #6E7582); padding-left: 138px; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
