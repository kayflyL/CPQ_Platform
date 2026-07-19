<script setup lang="ts">
/** 料号库管理（管理面）— 所有 L6+KP 料号逐条 CRUD。对应原型管理面料号库。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { partsApi, type PartMaster } from '@/api/serverConfig'
import { specFieldsFor, specSummary, type SpecField } from '@/constants/partSpecFields'

const parts = ref<PartMaster[]>([])
const categories = ref<string[]>([])
const category = ref<string>('all')
const search = ref('')
const loading = ref(false)
const modalVisible = ref(false)
const editing = ref<PartMaster | null>(null)
const form = ref<Partial<PartMaster>>({})
// 类别专用规格字段（命中字段族）：key → 值
const knownSpecs = ref<Record<string, any>>({})
// 扩展属性（兜底键值对）：剩余 specs key
const specsRows = ref<{ key: string; val: string }[]>([])

const categoryOptions = computed(() => categories.value.map(c => ({ label: c, value: c })))

const currentFields = computed<SpecField[]>(() => specFieldsFor(form.value.category))
const knownKeys = computed(() => new Set(currentFields.value.map(f => f.key)))

async function load() {
  loading.value = true
  try {
    const [list, cats] = await Promise.all([partsApi.list(), partsApi.categories()])
    parts.value = list.parts
    categories.value = cats.categories
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  let r = parts.value
  if (category.value !== 'all') r = r.filter(p => p.category === category.value)
  if (search.value) r = r.filter(p => p.pn.includes(search.value) || p.name.includes(search.value) || (p.description || '').includes(search.value))
  return r
})
const countOf = (cat: string) => parts.value.filter(p => p.category === cat).length
const summaryOf = (p: PartMaster) => specSummary(p.specs, p.category) || p.description || ''

function openNew() {
  editing.value = null
  form.value = { category: categories.value[0] || '' }
  initKnownSpecs(false)
  specsRows.value = []
  modalVisible.value = true
}
function openEdit(p: PartMaster) {
  editing.value = p
  form.value = { ...p }  // 先设 form，让 currentFields/knownKeys 按当前类别响应
  initKnownSpecs(true)   // 先补齐当前类别所有字段的默认值（保证 v-model 绑定响应式 key）
  const extra: { key: string; val: string }[] = []
  const kk = knownKeys.value
  for (const [k, v] of Object.entries(p.specs || {})) {
    const f = currentFields.value.find(ff => ff.key === k)
    if (f) {
      // tags 字段统一存 string[]；number/text 原样
      knownSpecs.value[k] = f.type === 'tags'
        ? (Array.isArray(v) ? v.map(String) : (v === null || v === undefined || v === '' ? [] : [String(v)]))
        : v
    } else {
      extra.push({ key: k, val: Array.isArray(v) ? v.join(', ') : String(v) })
    }
  }
  specsRows.value = extra
  modalVisible.value = true
}
// 初始化当前类别专用字段的 knownSpecs：keepExisting=true 保留已填值，仅补缺失字段默认值
function initKnownSpecs(keepExisting: boolean) {
  const next = keepExisting ? { ...knownSpecs.value } : {}
  for (const f of currentFields.value) {
    if (next[f.key] === undefined) next[f.key] = f.type === 'tags' ? [] : undefined
  }
  knownSpecs.value = next
}
function isTagsField(key: string): boolean {
  return currentFields.value.some(f => f.key === key && f.type === 'tags')
}
function addSpecRow() {
  specsRows.value.push({ key: '', val: '' })
}
function removeSpecRow(i: number) {
  specsRows.value.splice(i, 1)
}
// 类别切换时，把已填的专用字段值保留，新增字段补默认值（不强制清空，避免误操作丢数据）
function onCategoryChange() {
  initKnownSpecs(true)
}
// 合并专用字段 + 扩展属性 → specs 对象
function buildSpecs(): Record<string, any> {
  const out: Record<string, any> = {}
  const kk = knownKeys.value
  for (const f of currentFields.value) {
    const v = knownSpecs.value[f.key]
    if (v === undefined || v === null || v === '') continue
    if (f.type === 'tags') {
      if (Array.isArray(v) && v.length) out[f.key] = v
    } else if (f.type === 'number') {
      out[f.key] = Number(v)
    } else {
      const s = String(v).trim()
      if (s) out[f.key] = /^-?\d+(\.\d+)?$/.test(s) ? Number(s) : s
    }
  }
  for (const r of specsRows.value) {
    const k = (r.key || '').trim()
    if (!k || kk.has(k)) continue  // 跳过空 key 与已在专用区的 key，防重复
    const raw = (r.val ?? '').trim()
    if (raw === '') continue
    out[k] = /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : raw
  }
  return out
}
async function save() {
  try {
    const specs = buildSpecs()
    const payload: Partial<PartMaster> = {
      pn: form.value.pn, name: form.value.name, category: form.value.category,
      sub_type: form.value.sub_type, unit_price: form.value.unit_price,
      description: form.value.description, specs,
    }
    if (editing.value) await partsApi.update(editing.value.pn, payload)
    else await partsApi.create(payload)
    message.success('已保存')
    modalVisible.value = false
    load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}
async function remove(pn: string) {
  await partsApi.delete(pn)
  message.success('已删除')
  load()
}

onMounted(load)

</script>

<template>
  <div class="parts-library panel">
    <div class="lib-head">
      <h3>料号库 <span class="lib-count">{{ filtered.length }} / {{ parts.length }} 项</span></h3>
      <a-space>
        <a-input-search v-model:value="search" placeholder="搜料号/名称/描述" style="width:220px" size="small" allowClear />
        <a-button type="primary" size="small" @click="openNew">+ 新增料号</a-button>
      </a-space>
    </div>
    <div class="lib-body">
      <div class="cat-nav">
        <div :class="['cat-item', { active: category === 'all' }]" @click="category = 'all'">
          <span class="cat-name">全部</span><span class="cat-count">{{ parts.length }}</span>
        </div>
        <div v-for="c in categories" :key="c" :class="['cat-item', { active: category === c }]" @click="category = c">
          <span class="cat-name">{{ c }}</span><span class="cat-count">{{ countOf(c) }}</span>
        </div>
      </div>
      <div class="card-area">
        <div v-if="loading" class="grid-empty">加载中…</div>
        <div v-else-if="!filtered.length" class="grid-empty">无匹配料号，点击右上「+ 新增料号」添加</div>
        <div v-else class="card-grid">
          <div v-for="p in filtered" :key="p.pn" class="part-card" @click="openEdit(p)">
            <a-popconfirm title="删除该料号？" @confirm="remove(p.pn)" placement="top">
              <button class="pc-del" @click.stop>✕</button>
            </a-popconfirm>
            <div class="pc-top">
              <span class="pc-name">{{ p.name }}</span>
              <span class="pc-cat">{{ p.category }}</span>
            </div>
            <div class="pc-spec">{{ summaryOf(p) }}</div>
            <div class="pc-bottom">
              <span class="pc-pn">{{ p.pn }}</span>
              <span class="pc-price">{{ p.unit_price ? '¥' + p.unit_price : '—' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <a-modal :open="modalVisible" :title="editing ? '编辑料号' : '新增料号'" @ok="save"
             @cancel="modalVisible = false" width="640px" :destroyOnClose="true">
      <a-form layout="vertical">
        <div class="section-title">基础信息</div>
        <a-form-item label="料号 PN" required>
          <a-input v-model:value="form.pn" :disabled="!!editing" placeholder="如 S.E.M.0000351" />
        </a-form-item>
        <a-form-item label="名称" required><a-input v-model:value="form.name" /></a-form-item>
        <a-form-item label="描述"><a-input v-model:value="form.description" placeholder="如 PCBA_3.5''_Triple-mode 或 Cable_..._340mm" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="类别">
            <a-auto-complete v-model:value="form.category" :options="categoryOptions"
                             @change="onCategoryChange"
                             :filter-option="(input, option) => (option.value as string).toLowerCase().includes(input.toLowerCase())"
                             placeholder="选择或输入新类别" allow-clear />
          </a-form-item></a-col>
          <a-col :span="8"><a-form-item label="细分"><a-input v-model:value="form.sub_type" /></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="单价"><a-input-number v-model:value="form.unit_price" style="width:100%" :precision="2" /></a-form-item></a-col>
        </a-row>

        <template v-if="currentFields.length">
          <div class="section-title">规格参数 <span class="section-hint">· {{ form.category }}</span></div>
          <a-row :gutter="12">
            <a-col v-for="f in currentFields" :key="f.key" :span="12">
              <a-form-item :label="`${f.icon || ''} ${f.label}`">
                <a-input-number v-if="f.type === 'number'" v-model:value="knownSpecs[f.key]"
                                style="width:100%" :placeholder="`输入${f.label}`">
                  <template #addonAfter v-if="f.unit">{{ f.unit }}</template>
                </a-input-number>
                <a-select v-else-if="f.type === 'tags'" v-model:value="knownSpecs[f.key]" mode="tags"
                          style="width:100%" :placeholder="`输入后回车添加${f.label}`" :token-separators="[',']" />
                <a-input v-else v-model:value="knownSpecs[f.key]" :placeholder="`输入${f.label}`" />
              </a-form-item>
            </a-col>
          </a-row>
        </template>

        <div class="section-title">扩展属性 <span class="section-hint">· 其他规格键值对</span></div>
        <div class="specs-editor">
          <div v-for="(row, i) in specsRows" :key="i" class="spec-row">
            <a-input v-model:value="row.key" placeholder="名称 如 form" size="small" style="flex:1" />
            <a-input v-model:value="row.val" placeholder="值 如 2U 或 12" size="small" style="flex:1" />
            <a-button size="small" link danger @click="removeSpecRow(i)">删除</a-button>
          </div>
          <a-button size="small" type="dashed" block @click="addSpecRow">+ 添加属性</a-button>
        </div>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.panel { background: var(--cpq-bg-card, #14161c); border: 1px solid var(--cpq-border-primary, rgba(255,255,255,.10)); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.lib-count { font-size: 12px; font-weight: 400; color: var(--cpq-text-muted, #6E7582); margin-left: 6px; }
.lib-body { display: grid; grid-template-columns: 160px 1fr; gap: 14px; }
.cat-nav { display: flex; flex-direction: column; gap: 2px; }
.cat-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; color: var(--cpq-text-secondary, #9BA1AA); transition: all .15s; }
.cat-item:hover { background: rgba(255,255,255,.05); color: var(--cpq-text-primary, #E8ECEF); }
.cat-item.active { background: rgba(0,245,212,.12); color: var(--cpq-accent-primary, #00F5D4); font-weight: 600; }
.cat-count { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.cat-item.active .cat-count { color: var(--cpq-accent-primary, #00F5D4); }
.card-area { min-height: 200px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.grid-empty { color: var(--cpq-text-muted, #6E7582); text-align: center; padding: 40px; font-size: 13px; }
.part-card { position: relative; padding: 12px 14px; background: rgba(0,0,0,.2); border: 1px solid rgba(255,255,255,.10); border-radius: 10px; cursor: pointer; transition: all .2s; }
.part-card:hover { border-color: rgba(0,245,212,.4); background: rgba(0,245,212,.04); transform: translateY(-1px); }
.pc-del { position: absolute; top: 6px; right: 6px; width: 20px; height: 20px; border: none; background: transparent; color: var(--cpq-text-muted, #6E7582); font-size: 12px; cursor: pointer; border-radius: 4px; opacity: 0; transition: all .15s; }
.part-card:hover .pc-del { opacity: 1; }
.pc-del:hover { background: rgba(255,77,79,.15); color: #ff4d4f; }
.pc-top { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; padding-right: 20px; }
.pc-name { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-cat { font-size: 11px; color: var(--cpq-accent-primary, #00F5D4); background: rgba(0,245,212,.1); padding: 1px 6px; border-radius: 4px; white-space: nowrap; }
.pc-spec { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); line-height: 1.4; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 16px; }
.pc-bottom { display: flex; justify-content: space-between; align-items: center; }
.pc-pn { font-size: 11px; color: var(--cpq-text-muted, #6E7582); font-family: monospace; }
.pc-price { font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary, #00F5D4); }
.specs-editor { display: flex; flex-direction: column; gap: 6px; }
.spec-row { display: flex; gap: 6px; align-items: center; }
.section-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #e6e6e6); margin: 4px 0 8px; padding-left: 8px; border-left: 3px solid var(--cpq-accent, #1668dc); }
.section-hint { font-size: 11px; font-weight: 400; color: var(--cpq-text-secondary, rgba(255,255,255,.45)); }
</style>
