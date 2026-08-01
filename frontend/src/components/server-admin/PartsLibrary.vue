<script setup lang="ts">
/** 料号库管理（管理面）— 所有 L6+KP 料号逐条 CRUD。对应原型管理面料号库。
 *  分类三级，大类/STEP 由 l6.part_taxonomy 管理（左栏可增/改名/删，改名批量传播到所有相关料号）：
 *  一级大类（major_category，主导航）+ 二级子类（category，开放自由输入）；
 *  section（STEP 基准/前面板/后面板/电源）为快速筛选。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { UnorderedListOutlined, MenuFoldOutlined, UploadOutlined, DownloadOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { partsApi, type PartMaster, type PartSection, type PartMajorCategory } from '@/api/serverConfig'
import { specSummary, attrType, attrOptions, attrSchema, ATTR_KEY_OPTIONS, SUGGESTED_KEYS_BY_CATEGORY } from '@/constants/partSpecFields'
import { useSeriesStore } from '@/stores/series'

const parts = ref<PartMaster[]>([])
const total = ref(0)
const majorCats = ref<PartMajorCategory[]>([])  // 大类汇总（一级主导航 + 段内子类）
const sections = ref<PartSection[]>([])          // STEP 汇总（快速筛选用）
const categories = ref<string[]>([])      // 全部细类别（编辑表单的 category 自动补全用）
const majorCat = ref<string>('all')       // 一级大类筛选（主导航）
const section = ref<string>('all')        // STEP 快速筛选（基准/前面板/后面板/电源）
const cat2 = ref<string>('all')           // 段内子类二级筛选
const chassisFilter = ref<string>('all')   // 适用机型筛选（all / series名 / common / unclassified）
// 全平台系列权威源（system_config.server_series）：侧栏机型筛选 + chassis 字段下拉候选都读这里
const seriesStore = useSeriesStore()
const search = ref('')
const viewMode = ref<'card' | 'list'>('card')   // 卡片 / 列表 视图切换
const sortBy = ref<string>('')                   // 排序字段：name / unit_price
const loading = ref(false)
const pagination = ref({ current: 1, pageSize: 50 })
const modalVisible = ref(false)
const editing = ref<PartMaster | null>(null)
const form = ref<Partial<PartMaster>>({})
// 扩展属性：所有 specs 键值对（schema 驱动渲染）。val 类型随 attrType(key) 变（数组/字符串/数字）。
const specsRows = ref<{ key: string; val: any }[]>([])

// 导入相关状态
const importModalVisible = ref(false)
const importFile = ref<File | null>(null)
const importPreview = ref<any[]>([])
const importSummary = ref<any>({})
const importParsing = ref(false)
const importCommitting = ref(false)

const categoryOptions = computed(() => categories.value.map(c => ({ label: c, value: c })))
// 大类/STEP 选项来自 taxonomy（用户可增改），不再写死常量
const majorCategoryOptions = computed(() => majorCats.value.map(m => ({ label: m.major_category, value: m.major_category })))
const sectionOptions = computed(() => sections.value.map(s => ({ label: s.section, value: s.section })))

// 历史 values 缓存：每个 specs key 的已存在值列表（用于 free-tags 下拉）
const specValueCache = ref<Record<string, string[]>>({})

/** 从已加载的料号中提取某 key 的所有历史值（去重排序） */
function extractSpecValues(key: string): string[] {
  if (specValueCache.value[key]) return specValueCache.value[key]
  const set = new Set<string>()
  for (const p of parts.value) {
    const v = p.specs?.[key]
    if (v == null) continue
    if (Array.isArray(v)) v.forEach(x => x && set.add(String(x)))
    else set.add(String(v))
  }
  const arr = Array.from(set).sort()
  specValueCache.value[key] = arr
  return arr
}

/** 清空缓存（料号列表刷新后调用） */
function clearSpecValueCache() {
  specValueCache.value = {}
}

// 列表视图列定义（卡片/列表共享 filtered 数据与编辑弹窗）
const tableColumns = [
  { title: '料号 PN', dataIndex: 'pn', key: 'pn', width: 160 },
  { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '大类', dataIndex: 'major_category', key: 'major_category', width: 120 },
  { title: '类别', dataIndex: 'category', key: 'category', width: 110 },
  { title: '规格', key: 'summary', ellipsis: true },
  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', width: 110, align: 'right' as const },
  { title: '操作', key: 'op', width: 130, fixed: 'right' as const },
]

// 导入预览表格列
const importPreviewColumns = [
  { title: '行', dataIndex: '_row_index', width: 60 },
  { title: '操作', key: 'action', width: 90 },
  { title: '料号', dataIndex: 'pn', width: 140 },
  { title: '名称', dataIndex: 'name', ellipsis: true },
  { title: '类别', dataIndex: 'category', width: 120 },
  { title: '消息', dataIndex: 'message', ellipsis: true },
]

async function load() {
  loading.value = true
  clearSpecValueCache()
  try {
    const [sortKey, sortOrder] = sortBy.value ? sortBy.value.split('-') : [undefined, undefined]
    const [listRes, secs, cats] = await Promise.all([
      partsApi.list({
        major_category: majorCat.value === 'all' ? undefined : majorCat.value,
        section: section.value === 'all' ? undefined : section.value,
        category: cat2.value === 'all' ? undefined : cat2.value,
        search: search.value || undefined,
        chassis: chassisFilter.value === 'all' ? undefined : chassisFilter.value,
        page: pagination.value.current,
        page_size: pagination.value.pageSize,
        sort_by: sortKey,
        sort_order: sortOrder,
      }),
      partsApi.sections(),
      partsApi.categories(),
    ])
    parts.value = listRes.parts
    total.value = listRes.total
    sections.value = secs.sections
    categories.value = cats.categories
    // 大类汇总单独取：后端未重启（无 /major-categories）时不致命，降级为空大类导航
    try {
      const majors = await partsApi.majorCategories()
      majorCats.value = majors.major_categories
    } catch {
      majorCats.value = []
    }
    seriesStore.ensureSeries()
  } catch (e: any) {
    message.error(e.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// 当前大类下可选的子类（二级 chips）
const currentMajorCats = computed(() => {
  if (majorCat.value === 'all') return categories.value
  return majorCats.value.find(m => m.major_category === majorCat.value)?.categories || []
})

// 切换大类（主导航）→ 重置子类 + 分页 + 重载
function onMajorChange() {
  cat2.value = 'all'
  pagination.value.current = 1
  load()
}
// STEP 快速筛选 → 只重置分页 + 重载（与子类正交，不重置子类）
function onSectionChange() {
  pagination.value.current = 1
  load()
}
function onCat2Change() {
  pagination.value.current = 1
  load()
}
function onChassisFilterChange() {
  pagination.value.current = 1
  load()
}
function onSearch() {
  pagination.value.current = 1
  load()
}
function onSortChange() {
  pagination.value.current = 1
  load()
}

// ---- 大类/STEP 分类管理（增/改名/删；改名批量传播到所有相关料号）----
const taxModal = ref<{ open: boolean; mode: 'add' | 'rename'; kind: 'major' | 'step'; oldName?: string; name: string }>(
  { open: false, mode: 'add', kind: 'major', name: '' })
function openAddTax(kind: 'major' | 'step') {
  taxModal.value = { open: true, mode: 'add', kind, name: '' }
}
function openRenameTax(kind: 'major' | 'step', oldName: string) {
  taxModal.value = { open: true, mode: 'rename', kind, oldName, name: oldName }
}
async function saveTax() {
  const { mode, kind, name, oldName } = taxModal.value
  const n = (name || '').trim()
  if (!n) { message.warning('名称不能为空'); return }
  try {
    if (mode === 'add') await partsApi.taxonomy.add(kind, n)
    else await partsApi.taxonomy.rename(kind, oldName!, n)
    // 改名后若当前选中的正是被改的项，跟随到新名
    if (mode === 'rename' && kind === 'major' && majorCat.value === oldName) majorCat.value = n
    if (mode === 'rename' && kind === 'step' && section.value === oldName) section.value = n
    taxModal.value.open = false
    load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || e.message || '操作失败')
  }
}
async function deleteTax(kind: 'major' | 'step', name: string) {
  try {
    await partsApi.taxonomy.remove(kind, name)
    if (kind === 'major' && majorCat.value === name) { majorCat.value = 'all'; cat2.value = 'all' }
    if (kind === 'step' && section.value === name) section.value = 'all'
    load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || e.message || '删除失败')
  }
}

const summaryOf = (p: PartMaster) => specSummary(p.specs, p.category) || p.spec_text || ''

async function openNew() {
  editing.value = null
  form.value = {
    category: categories.value[0] || '',
    major_category: majorCats.value[0]?.major_category || '',
    section: sections.value[0]?.section || '',
  }
  specsRows.value = seedSuggested(form.value.category)
  // 确保 seriesStore.items 加载完成（chassis 下拉候选）
  await seriesStore.ensureSeries()
  modalVisible.value = true
}
async function openEdit(p: PartMaster) {
  editing.value = p
  form.value = { ...p }
  specsRows.value = specsToRows(p.specs)
  // 编辑时不再补齐建议键——尊重用户已删除的选择
  await seriesStore.ensureSeries()
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
// 子类切换时：补齐该子类建议键空行（大类/STEP 由用户从 taxonomy 下拉选）
function onCategoryChange() {
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
      major_category: form.value.major_category, section: form.value.section,
      unit_price: form.value.unit_price,
      spec_text: form.value.spec_text, description: form.value.description, specs,
    }
    if (editing.value) {
      await partsApi.update(editing.value.pn, payload)
    }
    else await partsApi.create(payload)
    message.success('已保存')
    modalVisible.value = false
    load()
  } catch (e: any) {
    // 兼容多种错误格式：axios response、Error message、字符串
    const detail = e.response?.data?.detail || e.message || String(e)
    message.error(detail)
  }
}
async function remove(pn: string) {
  await partsApi.delete(pn)
  message.success('已删除')
  load()
}

// 导入相关方法
function openImportModal() {
  importFile.value = null
  importPreview.value = []
  importSummary.value = {}
  importModalVisible.value = true
}
async function downloadTemplate() {
  try {
    const res = await partsApi.downloadTemplate()
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = 'parts_import_template.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    message.error('下载模板失败')
  }
}
function onImportFileSelect(file: File) {
  importFile.value = file
  importPreview.value = []
  importSummary.value = {}
  return false
}
async function previewImport() {
  if (!importFile.value) {
    message.warning('请先选择文件')
    return
  }
  importParsing.value = true
  try {
    const res = await partsApi.import(importFile.value, true)
    importPreview.value = res.preview || []
    importSummary.value = res.summary || {}
    if (!importPreview.value.length) message.info('未解析到任何数据行')
  } catch (e: any) {
    message.error('解析失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    importParsing.value = false
  }
}
async function confirmImport() {
  if (!importFile.value) return
  importCommitting.value = true
  try {
    const res = await partsApi.import(importFile.value, false)
    const s = res.summary || {}
    message.success(`导入完成：新增 ${s.new} · 更新 ${s.update} · 跳过 ${s.invalid}`)
    importModalVisible.value = false
    load()
  } catch (e: any) {
    message.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    importCommitting.value = false
  }
}
function resetImport() {
  importFile.value = null
  importPreview.value = []
  importSummary.value = {}
}
async function exportParts() {
  try {
    const res = await partsApi.export(section.value === 'all' ? undefined : section.value)
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `parts_${section.value || 'all'}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    message.success('已导出')
  } catch (e: any) {
    message.error('导出失败')
  }
}

const actionLabel = (a: string) => ({ new: '新增', update: '更新', invalid: '无效' } as any)[a] || a
const actionColor = (a: string) => ({ new: 'green', update: 'blue', invalid: 'default' } as any)[a] || 'default'

// 分页切换
function onPageChange(page: number, pageSize: number) {
  pagination.value.current = page
  pagination.value.pageSize = pageSize
  load()
}

// 响应式侧栏折叠
const sidebarCollapsed = ref(false)
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

onMounted(load)
</script>

<template>
  <div class="parts-library panel">
    <div class="lib-head">
      <div class="lib-head-left">
        <button class="sidebar-toggle" @click="toggleSidebar" title="折叠/展开分类导航">
          <UnorderedListOutlined v-if="sidebarCollapsed" />
          <MenuFoldOutlined v-else />
        </button>
        <h3>料号库 <span class="lib-count">{{ total }} 项</span></h3>
      </div>
      <a-space>
        <a-input-search v-model:value="search" placeholder="搜料号/名称" style="width:180px" size="small" allowClear @search="onSearch" />
        <a-select v-model:value="sortBy" style="width:120px" size="small" placeholder="排序" allowClear @change="onSortChange">
          <a-select-option value="name-asc">名称 A→Z</a-select-option>
          <a-select-option value="name-desc">名称 Z→A</a-select-option>
          <a-select-option value="unit_price-asc">价格 低→高</a-select-option>
          <a-select-option value="unit_price-desc">价格 高→低</a-select-option>
        </a-select>
        <a-radio-group v-model:value="viewMode" size="small" button-style="solid">
          <a-radio-button value="card">卡片</a-radio-button>
          <a-radio-button value="list">列表</a-radio-button>
        </a-radio-group>
        <a-button size="small" @click="openImportModal">
          <template #icon><UploadOutlined /></template>
          导入
        </a-button>
        <a-button size="small" @click="exportParts">
          <template #icon><DownloadOutlined /></template>
          导出
        </a-button>
        <a-button type="primary" size="small" @click="openNew">+ 新增料号</a-button>
      </a-space>
    </div>
    <div class="lib-body">
      <aside :class="['cat-nav', { collapsed: sidebarCollapsed }]">
        <div class="cat-section">
          <div class="cat-section-label"><span>大类</span><button class="tax-add" @click="openAddTax('major')" title="新增大类">+</button></div>
          <div :class="['cat-item', { active: majorCat === 'all' }]" @click="majorCat = 'all'; onMajorChange()">
            <span class="cat-name">全部</span><span class="cat-count">{{ total }}</span>
          </div>
          <div v-for="m in majorCats" :key="m.major_category" :class="['cat-item', { active: majorCat === m.major_category }]" @click="majorCat = m.major_category; onMajorChange()">
            <span class="cat-name">{{ m.major_category }}</span>
            <span class="cat-tools">
              <span class="cat-count">{{ m.count }}</span>
              <button class="cat-tool" title="重命名" @click.stop="openRenameTax('major', m.major_category)">✎</button>
              <a-popconfirm title="删除该大类？被料号使用时会拒绝" @confirm="deleteTax('major', m.major_category)">
                <button class="cat-tool cat-del" title="删除" @click.stop>✕</button>
              </a-popconfirm>
            </span>
          </div>
        </div>
        <div class="cat-section">
          <div class="cat-divider"></div>
          <div class="cat-section-label"><span>STEP 筛选</span><button class="tax-add" @click="openAddTax('step')" title="新增 STEP">+</button></div>
          <div :class="['cat-item', { active: section === 'all' }]" @click="section = 'all'; onSectionChange()">
            <span class="cat-name">全部</span>
          </div>
          <div v-for="s in sections" :key="s.section" :class="['cat-item', { active: section === s.section }]" @click="section = s.section; onSectionChange()">
            <span class="cat-name">{{ s.section }}</span>
            <span class="cat-tools">
              <span class="cat-count">{{ s.count }}</span>
              <button class="cat-tool" title="重命名" @click.stop="openRenameTax('step', s.section)">✎</button>
              <a-popconfirm title="删除该 STEP？被料号使用时会拒绝" @confirm="deleteTax('step', s.section)">
                <button class="cat-tool cat-del" title="删除" @click.stop>✕</button>
              </a-popconfirm>
            </span>
          </div>
        </div>
        <div v-if="seriesStore.values.length" class="cat-section">
          <div class="cat-divider"></div>
          <div class="cat-section-label">适用机型</div>
          <div :class="['cat-item', { active: chassisFilter === 'all' }]" @click="chassisFilter = 'all'; onChassisFilterChange()">
            <span class="cat-name">全部</span>
          </div>
          <div v-for="s in seriesStore.values" :key="s" :class="['cat-item', { active: chassisFilter === s }]" @click="chassisFilter = s; onChassisFilterChange()">
            <span class="cat-name">{{ s }}</span>
          </div>
        </div>
      </aside>
      <div class="card-area">
        <div v-if="currentMajorCats.length" class="subcat-bar">
          <div :class="['subcat-chip', { active: cat2 === 'all' }]" @click="cat2 = 'all'; onCat2Change()">全部子类</div>
          <div v-for="c in currentMajorCats" :key="c" :class="['subcat-chip', { active: cat2 === c }]" @click="cat2 = c; onCat2Change()">
            {{ c }}
          </div>
        </div>
        <div v-if="loading" class="grid-empty">加载中…</div>
        <div v-else-if="!parts.length" class="grid-empty">无匹配料号，点击右上「+ 新增料号」添加</div>
        <div v-else-if="viewMode === 'card'" class="card-grid">
          <div v-for="p in parts" :key="p.pn" class="part-card glass-light" @click="openEdit(p)">
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
        <template v-else>
          <a-table :data-source="parts" :columns="tableColumns" row-key="pn" size="small"
                   :pagination="{ current: pagination.current, pageSize: pagination.pageSize, total, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'], showTotal: (t:number) => `共 ${t} 项` }"
                   class="parts-table" @change="(pag: any) => { pagination.current = pag.current; pagination.pageSize = pag.pageSize; load() }">
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
        </template>
        <!-- 卡片视图分页 -->
        <div v-if="viewMode === 'card' && total > pagination.pageSize" class="card-pagination">
          <a-pagination
            :current="pagination.current"
            :page-size="pagination.pageSize"
            :total="total"
            :page-size-options="['20', '50', '100']"
            show-size-changer
            size="small"
            @change="onPageChange"
          />
        </div>
      </div>
    </div>

    <a-modal :open="modalVisible" :title="editing ? '编辑料号' : '新增料号'" @ok="save"
             @cancel="modalVisible = false" width="640px" :destroyOnClose="true">
      <a-form layout="vertical">
        <div class="section-title">基础信息</div>
        <a-form-item label="料号 PN" required>
          <a-input v-model:value="form.pn" placeholder="如 S.E.M.0000351" />
          <div class="field-hint">料号唯一标识，可自由修改</div>
        </a-form-item>
        <a-form-item label="名称" required><a-input v-model:value="form.name" /></a-form-item>
        <a-form-item label="规格"><a-input v-model:value="form.spec_text" placeholder="如 PCBA_3.5''_Triple-mode 或 Cable_..._340mm" /></a-form-item>
        <a-form-item label="说明"><a-textarea v-model:value="form.description" :rows="2" placeholder="一句话讲清楚这个料号是什么、用在哪、怎么选，给不熟悉的同事看" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="6"><a-form-item label="大类" required>
            <a-select v-model:value="form.major_category" :options="majorCategoryOptions" placeholder="选择大类" />
          </a-form-item></a-col>
          <a-col :span="6"><a-form-item label="子类">
            <a-auto-complete v-model:value="form.category" :options="categoryOptions"
                             @change="onCategoryChange"
                             :filter-option="(input: string, option: { value: string; label: string }) => (option.value as string).toLowerCase().includes(input.toLowerCase())"
                             placeholder="选择或输入子类" allow-clear />
          </a-form-item></a-col>
          <a-col :span="6"><a-form-item label="STEP 部段" required>
            <a-select v-model:value="form.section" :options="sectionOptions" placeholder="基准/前面板/后面板/电源" />
          </a-form-item></a-col>
          <a-col :span="6"><a-form-item label="单价"><a-input-number v-model:value="form.unit_price" style="width:100%" :precision="2" /></a-form-item></a-col>
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
                      :options="(row.key === 'chassis' ? seriesStore.items : extractSpecValues(row.key).map(v => ({ label: v, value: v })))"
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

    <!-- 批量导入 Modal -->
    <a-modal :open="importModalVisible" title="批量导入料号" width="860px" :footer="null" @cancel="importModalVisible = false; resetImport()">
      <div class="import-modal">
        <div v-if="!importPreview.length" class="import-step1">
          <a-upload :before-upload="onImportFileSelect" :max-count="1" accept=".xlsx,.xls" :file-list="[]">
            <a-button>
              <template #icon><InboxOutlined /></template>
              选择 Excel 文件
            </a-button>
          </a-upload>
          <span v-if="importFile" class="import-filename">{{ importFile.name }}</span>

          <div class="import-actions">
            <a-button type="link" @click="downloadTemplate">下载导入模板</a-button>
            <a-button type="primary" :loading="importParsing" :disabled="!importFile" @click="previewImport">
              解析预览
            </a-button>
          </div>
          <p class="import-tip">先下载模板按格式填写；导入前会展示逐行预览（新增 / 更新），确认后才真正写入。</p>
        </div>

        <div v-else class="import-step2">
          <div class="import-summary">
            <a-tag color="green">新增 {{ importSummary.new || 0 }}</a-tag>
            <a-tag color="blue">更新 {{ importSummary.update || 0 }}</a-tag>
            <a-tag v-if="importSummary.invalid" color="default">无效 {{ importSummary.invalid }}</a-tag>
            <span class="import-total">共 {{ importSummary.total }} 行</span>
          </div>
          <a-table :data-source="importPreview" :columns="importPreviewColumns" :pagination="{ pageSize: 50 }" size="small" :scroll="{ y: 340 }" row-key="_row_index">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'action'">
                <a-tag :color="actionColor(record.action)">{{ actionLabel(record.action) }}</a-tag>
              </template>
            </template>
          </a-table>
          <div class="import-actions">
            <a-button @click="resetImport">重新选择</a-button>
            <a-button type="primary" :loading="importCommitting" :disabled="!((importSummary.new || 0) + (importSummary.update || 0))" @click="confirmImport">确认导入</a-button>
          </div>
        </div>
      </div>
    </a-modal>

    <!-- 分类管理 Modal（新增 / 重命名 大类·STEP）-->
    <a-modal :open="taxModal.open" :title="(taxModal.mode === 'add' ? '新增' : '重命名') + (taxModal.kind === 'major' ? '大类' : ' STEP')" @ok="saveTax" @cancel="taxModal.open = false" :destroyOnClose="true">
      <a-input v-model:value="taxModal.name" :placeholder="taxModal.kind === 'major' ? '大类名称' : 'STEP 名称（如 基准件）'" @pressEnter="saveTax" />
      <div class="field-hint" v-if="taxModal.mode === 'rename'">改名会同步到所有用了该分类的料号。</div>
    </a-modal>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.lib-head-left { display: flex; align-items: center; gap: 8px; }
.sidebar-toggle { width: 32px; height: 32px; border: 1px solid var(--cpq-overlay-w15); background: transparent; color: var(--cpq-text-secondary); border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.sidebar-toggle:hover { background: var(--cpq-overlay-w10); color: var(--cpq-text-primary); }
.lib-head h3 { margin: 0; font-size: 15px; }
.lib-count { font-size: 12px; font-weight: 400; color: var(--cpq-text-muted, #6E7582); margin-left: 6px; }
.lib-body { display: grid; grid-template-columns: 160px 1fr; gap: 14px; transition: grid-template-columns .2s; }
.lib-body:has(.cat-nav.collapsed) { grid-template-columns: 0px 1fr; }
.cat-nav { display: flex; flex-direction: column; gap: 2px; overflow-x: hidden; overflow-y: auto; max-height: calc(100vh - 130px); padding-right: 2px; transition: width .2s, opacity .2s; }
.cat-nav::-webkit-scrollbar { width: 5px; }
.cat-nav::-webkit-scrollbar-thumb { background: var(--cpq-overlay-w15); border-radius: 3px; }
.cat-nav.collapsed { width: 0; opacity: 0; max-height: none; }
.cat-section { display: flex; flex-direction: column; gap: 2px; }
.cat-divider { height: 1px; background: var(--cpq-overlay-w10); margin: 8px 0; }
.cat-section-label { display: flex; justify-content: space-between; align-items: center; font-size: 11px; font-weight: 600; color: var(--cpq-text-muted, #6E7582); padding: 4px 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.tax-add { margin-left: auto; border: none; background: transparent; color: var(--cpq-text-muted, #6E7582); font-size: 15px; line-height: 1; width: 18px; height: 18px; cursor: pointer; border-radius: 4px; }
.tax-add:hover { background: var(--cpq-overlay-w15); color: var(--cpq-accent-primary, #1677FF); }
.cat-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; color: var(--cpq-text-secondary, #9BA1AA); transition: all .15s; white-space: nowrap; }
.cat-item:hover { background: var(--cpq-overlay-w5); color: var(--cpq-text-primary, #E8ECEF); }
.cat-item.active { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary, #1677FF); font-weight: 600; }
.cat-count { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.cat-item.active .cat-count { color: var(--cpq-accent-primary, #1677FF); }
.cat-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.cat-tools { display: inline-flex; align-items: center; gap: 1px; flex-shrink: 0; }
.cat-tool { width: 18px; height: 18px; border: none; background: transparent; color: var(--cpq-text-muted, #6E7582); font-size: 11px; cursor: pointer; border-radius: 4px; opacity: 0; transition: opacity .15s, background .15s; display: inline-flex; align-items: center; justify-content: center; }
.cat-item:hover .cat-tool { opacity: 1; }
.cat-tool:hover { background: var(--cpq-overlay-w15); color: var(--cpq-text-primary, #E8ECEF); }
.cat-tool.cat-del:hover { background: var(--cpq-overlay-danger15); color: var(--cpq-accent-danger, #ff4d4f); }
.card-area { min-height: 200px; }
.subcat-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.subcat-chip { font-size: 12px; padding: 3px 10px; border-radius: 12px; cursor: pointer; color: var(--cpq-text-secondary, #9BA1AA); background: var(--cpq-overlay-w5); transition: all .15s; }
.subcat-chip:hover { background: var(--cpq-overlay-w10); color: var(--cpq-text-primary, #E8ECEF); }
.subcat-chip.active { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary, #1677FF); font-weight: 600; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.card-pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
.grid-empty { color: var(--cpq-text-muted, #6E7582); text-align: center; padding: 40px; font-size: 13px; }
.parts-table :deep(.ant-table) { background: transparent; }
.parts-table :deep(.ant-table-thead > tr > th) { background: var(--cpq-overlay-w8); font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); }
.parts-table :deep(.ant-table-tbody > tr > td) { font-size: 13px; }
.parts-table :deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-w6); }
.tbl-pn { font-family: monospace; font-size: 12px; color: var(--cpq-text-muted, #6E7582); }
.tbl-cat { font-size: 11px; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10); padding: 1px 6px; border-radius: 4px; }
.part-card { position: relative; padding: 12px 14px; cursor: pointer; transition: transform .2s, box-shadow .2s; border-radius: 0; }
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
.field-hint { font-size: 11px; color: var(--cpq-text-muted, #6E7582); margin-top: 2px; }
/* 导入弹窗样式 */
.import-modal { min-height: 200px; }
.import-step1 { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
.import-filename { color: var(--cpq-text-secondary); font-size: 13px; }
.import-actions { display: flex; gap: 8px; margin-top: 8px; }
.import-tip { font-size: 12px; color: var(--cpq-text-muted); line-height: 1.6; }
.import-step2 { display: flex; flex-direction: column; gap: 12px; }
.import-summary { display: flex; gap: 8px; align-items: center; }
.import-total { color: var(--cpq-text-secondary); font-size: 12px; margin-left: auto; }
/* 响应式适配 */
@media (max-width: 768px) {
  .lib-body { grid-template-columns: 1fr; }
  .cat-nav { position: fixed; left: 0; top: 0; bottom: 0; width: 200px; background: var(--cpq-bg); z-index: 100; box-shadow: 2px 0 12px rgba(0,0,0,.3); transform: translateX(-100%); transition: transform .2s; }
  .cat-nav:not(.collapsed) { transform: translateX(0); }
  .cat-nav.collapsed { transform: translateX(-100%); }
  .card-grid { grid-template-columns: 1fr; }
}
</style>