<script setup lang="ts">
/** 料号库管理（管理面）— 所有 L6+KP 料号逐条 CRUD。对应原型管理面料号库。
 *  分类两级：一级部段（section：基准/前面板/后面板/电源，对应报价表4个STEP）+ 段内细类别（category）。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { partsApi, type PartMaster, type PartSection } from '@/api/serverConfig'
import { specSummary, attrType, attrOptions, attrSchema, ATTR_KEY_OPTIONS, SUGGESTED_KEYS_BY_CATEGORY } from '@/constants/partSpecFields'
import { useSeries } from '@/composables/useSeries'
import { SECTION_ORDER, defaultSectionFor } from '@/constants/partSections'

const parts = ref<PartMaster[]>([])
const sections = ref<PartSection[]>([])
const categories = ref<string[]>([])      // 全部细类别（编辑表单的 category 自动补全用）
const section = ref<string>('all')         // 一级部段筛选
const cat2 = ref<string>('all')            // 段内细类别二级筛选
const chassisFilter = ref<string>('all')   // 适用机型筛选（all / series名 / common / unclassified）
// 全平台系列权威源（system_config.server_series）：侧栏机型筛选 + chassis 字段下拉候选都读这里
const { items: seriesItems, values: seriesValues, ensureSeries } = useSeries()
const search = ref('')
const viewMode = ref<'card' | 'list'>('card')   // 卡片 / 列表 视图切换
const loading = ref(false)
const modalVisible = ref(false)
const editing = ref<PartMaster | null>(null)
const form = ref<Partial<PartMaster>>({})
// 扩展属性：所有 specs 键值对（schema 驱动渲染）。val 类型随 attrType(key) 变（数组/字符串/数字）。
const specsRows = ref<{ key: string; val: any }[]>([])

const categoryOptions = computed(() => categories.value.map(c => ({ label: c, value: c })))
const sectionOptions = SECTION_ORDER.map(s => ({ label: s, value: s }))

// 列表视图列定义（卡片/列表共享 filtered 数据与编辑弹窗）
const tableColumns = [
  { title: '料号 PN', dataIndex: 'pn', key: 'pn', width: 160 },
  { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '部段', dataIndex: 'section', key: 'section', width: 90 },
  { title: '类别', dataIndex: 'category', key: 'category', width: 110 },
  { title: '规格 / 描述', key: 'summary', ellipsis: true },
  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', width: 110, align: 'right' as const },
  { title: '操作', key: 'op', width: 130, fixed: 'right' as const },
]

async function load() {
  loading.value = true
  try {
    const [list, secs, cats] = await Promise.all([
      partsApi.list(),
      partsApi.sections(),
      partsApi.categories(),
    ])
    parts.value = list.parts
    sections.value = secs.sections
    categories.value = cats.categories
    ensureSeries()  // 异步加载全平台系列（权威源），不阻塞料号列表
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

// 当前部段下可选的细类别（二级 chips）
const currentSectionCats = computed(() => {
  if (section.value === 'all') return categories.value
  return sections.value.find(s => s.section === section.value)?.categories || []
})
const countOfSection = (sec: string) => sections.value.find(s => s.section === sec)?.count ?? 0
const countOfCat = (cat: string) => parts.value.filter(p => p.category === cat).length

// 机型筛选逻辑
const getPartChassis = (p: PartMaster): string[] => {
  const ch = p.specs?.chassis
  if (Array.isArray(ch)) return ch
  if (typeof ch === 'string' && ch) return [ch]
  return []
}
const isCommonPart = (p: PartMaster): boolean => {
  const ch = getPartChassis(p)
  return seriesValues.value.length > 0 && seriesValues.value.every(s => ch.includes(s))
}
const isUnclassifiedPart = (p: PartMaster): boolean => {
  return getPartChassis(p).length === 0
}
const countOfChassis = (series: string): number => {
  return parts.value.filter(p => getPartChassis(p).includes(series)).length
}
const countOfCommon = (): number => parts.value.filter(isCommonPart).length
const countOfUnclassified = (): number => parts.value.filter(isUnclassifiedPart).length

// 自由标签历史候选：从已加载料号的 specs 聚合每个 key 出现过的值，给 free-tags 控件做"以前填过"的下拉联想。
// 仅服务于 free-tags（chassis/form/drive_bays 等）；enum-* 有自己的静态 options，不走这里。
const historyOptionsByKey = computed(() => {
  const map: Record<string, { label: string; value: string }[]> = {}
  for (const p of parts.value) {
    const specs = p.specs
    if (!specs) continue
    for (const [k, v] of Object.entries(specs)) {
      const arr = Array.isArray(v) ? v : (v === null || v === undefined || v === '' ? [] : [v])
      if (!arr.length) continue
      const bucket = map[k] || (map[k] = [])
      for (const x of arr) {
        const s = String(x)
        if (s && !bucket.some(o => o.value === s)) bucket.push({ label: s, value: s })
      }
    }
  }
  return map
})
const historyOptions = (key: string) => historyOptionsByKey.value[key] || []
// free-tags 候选按 key 选源：chassis 走系列权威源（system_config.server_series），
// 其余 free-tags（form/drive_bays 等）走历史聚合。chassis 仍可自由输入新值（tags 模式）。
const freeTagOptions = (key: string) => key === 'chassis' ? seriesItems.value : historyOptions(key)

const filtered = computed(() => {
  let r = parts.value
  if (section.value !== 'all') r = r.filter(p => p.section === section.value)
  if (cat2.value !== 'all') r = r.filter(p => p.category === cat2.value)
  if (search.value) r = r.filter(p => p.pn.includes(search.value) || p.name.includes(search.value) || (p.description || '').includes(search.value))
  // 机型筛选
  if (chassisFilter.value === 'common') {
    r = r.filter(isCommonPart)
  } else if (chassisFilter.value === 'unclassified') {
    r = r.filter(isUnclassifiedPart)
  } else if (chassisFilter.value !== 'all') {
    r = r.filter(p => getPartChassis(p).includes(chassisFilter.value))
  }
  return r
})
function onSectionChange() { cat2.value = 'all' }   // 切段清空二级筛选
const summaryOf = (p: PartMaster) => specSummary(p.specs, p.category) || p.description || ''

function openNew() {
  editing.value = null
  form.value = { category: categories.value[0] || '', section: defaultSectionFor(categories.value[0]) || SECTION_ORDER[0] }
  specsRows.value = seedSuggested(form.value.category)
  modalVisible.value = true
}
function openEdit(p: PartMaster) {
  editing.value = p
  form.value = { ...p }
  specsRows.value = specsToRows(p.specs)
  // 补齐该类别建议键（不覆盖已有）
  const existing = new Set(specsRows.value.map(r => r.key))
  for (const k of (SUGGESTED_KEYS_BY_CATEGORY[p.category] || [])) {
    if (!existing.has(k)) specsRows.value.push(emptyRow(k))
  }
  modalVisible.value = true
}
// specs → 编辑行（按 schema 归一 val 类型）
function specsToRows(specs: Record<string, any> | undefined): { key: string; val: any }[] {
  const rows: { key: string; val: any }[] = []
  for (const [k, v] of Object.entries(specs || {})) {
    rows.push({ key: k, val: coerceVal(k, v) })
  }
  return rows
}
// 按 attrType 把存储值归一成控件能直接绑定的形态
function coerceVal(key: string, v: any): any {
  const t = attrType(key)
  if (t === 'enum-multi' || t === 'free-tags') {
    if (Array.isArray(v)) return v.map(String)
    if (v === null || v === undefined || v === '') return []
    return [String(v)]
  }
  if (t === 'number') {
    if (v === '' || v === null || v === undefined) return undefined
    const n = Number(v); return Number.isNaN(n) ? undefined : n
  }
  // enum-single / text
  if (Array.isArray(v)) return v.join(', ')
  return v === null || v === undefined ? '' : String(v)
}
function emptyRow(key: string): { key: string; val: any } {
  const t = attrType(key)
  return { key, val: (t === 'enum-multi' || t === 'free-tags') ? [] : (t === 'number' ? undefined : '') }
}
// 类别建议键 → 空行列表
function seedSuggested(category: string | undefined): { key: string; val: any }[] {
  return (SUGGESTED_KEYS_BY_CATEGORY[category || ''] || []).map(emptyRow)
}
// 键改了→按新键类型归一 val（避免数组/标量错位）
function onKeyChange(row: { key: string; val: any }) {
  row.val = coerceVal(row.key, row.val)
}
function addSpecRow() {
  specsRows.value.push({ key: '', val: [] })  // 未登记键默认 free-tags
}
function removeSpecRow(i: number) {
  specsRows.value.splice(i, 1)
}
// 类别切换时：若部段未手填则按映射补默认值；并补齐该类别建议键空行
function onCategoryChange() {
  if (!form.value.section && form.value.category) {
    const s = defaultSectionFor(form.value.category)
    if (s) form.value.section = s
  }
  const existing = new Set(specsRows.value.map(r => r.key))
  for (const k of (SUGGESTED_KEYS_BY_CATEGORY[form.value.category || ''] || [])) {
    if (!existing.has(k)) specsRows.value.push(emptyRow(k))
  }
}
// 扩展属性 → specs 对象（enum-multi/free-tags 存数组，number 存数字，其余存字符串）
function buildSpecs(): Record<string, any> {
  const out: Record<string, any> = {}
  for (const r of specsRows.value) {
    const k = (r.key || '').trim()
    if (!k) continue
    const t = attrType(k)
    const v = r.val
    if (t === 'enum-multi' || t === 'free-tags') {
      if (Array.isArray(v) && v.length) {
        const arr = v.map(String).filter(x => x !== '')
        if (arr.length) out[k] = arr
      }
    } else if (t === 'number') {
      if (v !== undefined && v !== null && v !== '') out[k] = Number(v)
    } else {
      const s = String(v ?? '').trim()
      if (s) out[k] = /^-?\d+(\.\d+)?$/.test(s) ? Number(s) : s
    }
  }
  return out
}
async function save() {
  try {
    const specs = buildSpecs()
    const payload: Partial<PartMaster> = {
      pn: form.value.pn, name: form.value.name, category: form.value.category,
      section: form.value.section, unit_price: form.value.unit_price,
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
  <div class="parts-library panel glass">
    <div class="lib-head">
      <h3>料号库 <span class="lib-count">{{ filtered.length }} / {{ parts.length }} 项</span></h3>
      <a-space>
        <a-input-search v-model:value="search" placeholder="搜料号/名称/描述" style="width:220px" size="small" allowClear />
        <a-radio-group v-model:value="viewMode" size="small" button-style="solid">
          <a-radio-button value="card">卡片</a-radio-button>
          <a-radio-button value="list">列表</a-radio-button>
        </a-radio-group>
        <a-button type="primary" size="small" @click="openNew">+ 新增料号</a-button>
      </a-space>
    </div>
    <div class="lib-body">
      <div class="cat-nav">
        <div :class="['cat-item', { active: section === 'all' }]" @click="section = 'all'; onSectionChange()">
          <span class="cat-name">全部</span><span class="cat-count">{{ parts.length }}</span>
        </div>
        <div v-for="s in SECTION_ORDER" :key="s" :class="['cat-item', { active: section === s }]" @click="section = s; onSectionChange()">
          <span class="cat-name">{{ s }}</span><span class="cat-count">{{ countOfSection(s) }}</span>
        </div>
        <div v-if="seriesValues.length" class="cat-divider"></div>
        <div v-if="seriesValues.length" class="cat-section-title">适用机型</div>
        <div v-if="seriesValues.length" :class="['cat-item', { active: chassisFilter === 'all' }]" @click="chassisFilter = 'all'">
          <span class="cat-name">全部</span><span class="cat-count">{{ parts.length }}</span>
        </div>
        <div v-for="s in seriesValues" :key="s" :class="['cat-item', { active: chassisFilter === s }]" @click="chassisFilter = s">
          <span class="cat-name">{{ s }}</span><span class="cat-count">{{ countOfChassis(s) }}</span>
        </div>
        <div :class="['cat-item', { active: chassisFilter === 'common' }]" @click="chassisFilter = 'common'">
          <span class="cat-name">通用</span><span class="cat-count">{{ countOfCommon() }}</span>
        </div>
        <div :class="['cat-item', { active: chassisFilter === 'unclassified' }]" @click="chassisFilter = 'unclassified'">
          <span class="cat-name">未分类</span><span class="cat-count">{{ countOfUnclassified() }}</span>
        </div>
      </div>
      <div class="card-area">
        <div v-if="currentSectionCats.length" class="subcat-bar">
          <div :class="['subcat-chip', { active: cat2 === 'all' }]" @click="cat2 = 'all'">全部细类</div>
          <div v-for="c in currentSectionCats" :key="c" :class="['subcat-chip', { active: cat2 === c }]" @click="cat2 = c">
            {{ c }}<span class="subcat-count">{{ countOfCat(c) }}</span>
          </div>
        </div>
        <div v-if="loading" class="grid-empty">加载中…</div>
        <div v-else-if="!filtered.length" class="grid-empty">无匹配料号，点击右上「+ 新增料号」添加</div>
        <div v-else-if="viewMode === 'card'" class="card-grid">
          <div v-for="p in filtered" :key="p.pn" class="part-card glass-light" @click="openEdit(p)">
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
        <a-table v-else :data-source="filtered" :columns="tableColumns" row-key="pn" size="small"
                 :pagination="{ pageSize: 20, size: 'small', showTotal: (t:number) => `共 ${t} 项` }"
                 class="parts-table">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'pn'"><span class="tbl-pn">{{ record.pn }}</span></template>
            <template v-else-if="column.key === 'category'"><span class="tbl-cat">{{ record.category }}</span></template>
            <template v-else-if="column.key === 'summary'">{{ summaryOf(record) }}</template>
            <template v-else-if="column.key === 'unit_price'">{{ record.unit_price ? '¥' + record.unit_price : '—' }}</template>
            <template v-else-if="column.key === 'op'">
              <a-button size="small" link @click="openEdit(record)">编辑</a-button>
              <a-popconfirm title="删除该料号？" @confirm="remove(record.pn)">
                <a-button size="small" link danger>删除</a-button>
              </a-popconfirm>
            </template>
          </template>
        </a-table>
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
          <a-col :span="8"><a-form-item label="部段" required>
            <a-select v-model:value="form.section" :options="sectionOptions" placeholder="选择部段" />
          </a-form-item></a-col>
          <a-col :span="8"><a-form-item label="类别">
            <a-auto-complete v-model:value="form.category" :options="categoryOptions"
                             @change="onCategoryChange"
                             :filter-option="(input: string, option: { value: string; label: string }) => (option.value as string).toLowerCase().includes(input.toLowerCase())"
                             placeholder="选择或输入细类别" allow-clear />
          </a-form-item></a-col>
          <a-col :span="8"><a-form-item label="单价"><a-input-number v-model:value="form.unit_price" style="width:100%" :precision="2" /></a-form-item></a-col>
        </a-row>

        <div class="section-title">扩展属性 <span class="section-hint">· 适用于槽位 / 机型 / 规格</span></div>
        <div class="specs-editor">
          <div v-for="(row, i) in specsRows" :key="i" class="spec-row">
            <a-auto-complete v-model:value="row.key" :options="ATTR_KEY_OPTIONS" size="small" style="flex:1"
                             @change="() => onKeyChange(row)"
                             :filter-option="(input: string, option: { value: string; label: string }) => (option.value as string).toLowerCase().includes(input.toLowerCase())"
                             placeholder="属性名（如 io_slot）" allow-clear />
            <a-select v-if="attrType(row.key) === 'enum-single'" v-model:value="row.val" :options="attrOptions(row.key)"
                      size="small" style="flex:1.4" placeholder="选择" allow-clear />
            <a-select v-else-if="attrType(row.key) === 'enum-multi'" v-model:value="row.val" mode="multiple"
                      :options="attrOptions(row.key)" size="small" style="flex:1.4" placeholder="选择（可多选）" />
            <a-select v-else-if="attrType(row.key) === 'free-tags'" v-model:value="row.val" mode="tags"
                      :options="freeTagOptions(row.key)"
                      :token-separators="[',']" size="small" style="flex:1.4" placeholder="输入后回车添加" />
            <a-input-number v-else-if="attrType(row.key) === 'number'" v-model:value="row.val" size="small" style="flex:1.4">
              <template #addonAfter v-if="attrSchema(row.key)?.unit">{{ attrSchema(row.key)?.unit }}</template>
            </a-input-number>
            <a-input v-else v-model:value="row.val" size="small" style="flex:1.4" placeholder="输入值" />
            <a-button size="small" link danger @click="removeSpecRow(i)">删除</a-button>
          </div>
          <a-button size="small" type="dashed" block @click="addSpecRow">+ 添加属性</a-button>
        </div>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.lib-count { font-size: 12px; font-weight: 400; color: var(--cpq-text-muted, #6E7582); margin-left: 6px; }
.lib-body { display: grid; grid-template-columns: 160px 1fr; gap: 14px; }
.cat-nav { display: flex; flex-direction: column; gap: 2px; }
.cat-divider { height: 1px; background: var(--cpq-overlay-w10); margin: 8px 0; }
.cat-section-title { font-size: 11px; font-weight: 600; color: var(--cpq-text-muted, #6E7582); padding: 4px 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.cat-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; color: var(--cpq-text-secondary, #9BA1AA); transition: all .15s; }
.cat-item:hover { background: var(--cpq-overlay-w5); color: var(--cpq-text-primary, #E8ECEF); }
.cat-item.active { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary, #1677FF); font-weight: 600; }
.cat-count { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.cat-item.active .cat-count { color: var(--cpq-accent-primary, #1677FF); }
.card-area { min-height: 200px; }
.subcat-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.subcat-chip { font-size: 12px; padding: 3px 10px; border-radius: 12px; cursor: pointer; color: var(--cpq-text-secondary, #9BA1AA); background: var(--cpq-overlay-w5); transition: all .15s; }
.subcat-chip:hover { background: var(--cpq-overlay-w10); color: var(--cpq-text-primary, #E8ECEF); }
.subcat-chip.active { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary, #1677FF); font-weight: 600; }
.subcat-count { margin-left: 4px; font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.subcat-chip.active .subcat-count { color: var(--cpq-accent-primary, #1677FF); }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.grid-empty { color: var(--cpq-text-muted, #6E7582); text-align: center; padding: 40px; font-size: 13px; }
.parts-table :deep(.ant-table) { background: transparent; }
.parts-table :deep(.ant-table-thead > tr > th) { background: var(--cpq-overlay-w8); font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); }
.parts-table :deep(.ant-table-tbody > tr > td) { font-size: 13px; }
.parts-table :deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-w6); }
.tbl-pn { font-family: monospace; font-size: 12px; color: var(--cpq-text-muted, #6E7582); }
.tbl-cat { font-size: 11px; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10); padding: 1px 6px; border-radius: 4px; }
.part-card { position: relative; padding: 12px 14px; cursor: pointer; transition: transform .2s, box-shadow .2s; }
.part-card:hover { transform: translateY(-2px); }
.pc-del { position: absolute; top: 6px; right: 6px; width: 20px; height: 20px; border: none; background: transparent; color: var(--cpq-text-muted, #6E7582); font-size: 12px; cursor: pointer; border-radius: 4px; opacity: 0; transition: all .15s; }
.part-card:hover .pc-del { opacity: 1; }
.pc-del:hover { background: var(--cpq-overlay-danger15); color: var(--cpq-accent-danger); }
.pc-top { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; padding-right: 20px; }
.pc-name { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-cat { font-size: 11px; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10); padding: 1px 6px; border-radius: 4px; white-space: nowrap; }
.pc-spec { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); line-height: 1.4; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 16px; }
.pc-bottom { display: flex; justify-content: space-between; align-items: center; }
.pc-pn { font-size: 11px; color: var(--cpq-text-muted, #6E7582); font-family: monospace; }
.pc-price { font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary, #1677FF); }
.specs-editor { display: flex; flex-direction: column; gap: 6px; }
.spec-row { display: flex; gap: 6px; align-items: center; }
.section-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #e6e6e6); margin: 4px 0 8px; padding-left: 8px; border-left: 3px solid var(--cpq-accent, #1668dc); }
.section-hint { font-size: 11px; font-weight: 400; color: var(--cpq-text-secondary, rgba(255,255,255,.45)); }
</style>
