<script setup lang="ts">
/** BOM案例库（选型配置 · /strategies/selection 的「BOM案例库」模式）。
 *  业务定位：典型配置方案库（原始需求 → BOM单），按 系列/平台/机型 分类。
 *  - 详情直出「机箱(L6)配置单 + 配件(KP)配置单」；
 *  - L6 可编辑且部分行跟随 KP 自动变化（GPU 电源线=GPU 总数、散热器=CPU 总数）；
 *  - kp_lines 只引用 kp_parts；L6 保存时固化为快照（案例自包含）；
 *  - 配置页不留价格快照。 */
import { ref, computed, watch, onMounted } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { bomCaseApi, kpCatalogApi, type BomCase, type BomKpLine, type KpCategory, type KpPart, type L6Row } from '@/api/bomCases'
import { catalogApi, baseConfigApi, bomTemplateApi, type ServerModel, type BaseConfig, type BomTemplate } from '@/api/serverConfig'

const cases = ref<BomCase[]>([])
const loading = ref(false)
const search = ref('')
const tagFilter = ref<string[]>([])

// 分类筛选：系列 / 平台 / 机型
const serverTypeFilter = ref<string | null>(null)
const seriesFilter = ref<string | null>(null)
const modelFilter = ref<number | null>(null)

const drawerOpen = ref(false)
const editing = ref<BomCase | null>(null)
const saving = ref(false)

// ── 表单模型（无价格快照）──
const form = ref({
  name: '',
  scenario_tags: [] as string[],
  model_id: null as number | null,
  base_config_id: null as number | null,
  bom_template_id: null as number | null,
  requirement: '',
  l6_config_desc: '',
  kp_lines: [] as BomKpLine[],
  l6_rows: [] as L6Row[],
  notes: '',
  enabled: true,
})

const cats = ref<KpCategory[]>([])
const partsByCat = ref<Record<number, KpPart[]>>({})
const models = ref<ServerModel[]>([])
const baseConfigs = ref<BaseConfig[]>([])
const templates = ref<BomTemplate[]>([])

// ── 分类选项（数据驱动）──
const serverTypes = computed(() => [...new Set(cases.value.map(c => c.server_type).filter(Boolean))].sort() as string[])
const seriesList = computed(() => [...new Set(cases.value.map(c => c.series).filter(Boolean))].sort() as string[])
const modelList = computed(() => {
  const m = new Map<number, string>()
  cases.value.forEach(c => { if (c.model_id) m.set(c.model_id, c.model_name || '') })
  return [...m.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
})
const allTags = computed(() => {
  const s = new Set<string>()
  cases.value.forEach(c => (c.scenario_tags || []).forEach(t => s.add(t)))
  return [...s].sort()
})
function countBy(fn: (c: BomCase) => boolean): number { return cases.value.filter(fn).length }

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return cases.value.filter(c => {
    if (serverTypeFilter.value && c.server_type !== serverTypeFilter.value) return false
    if (seriesFilter.value && c.series !== seriesFilter.value) return false
    if (modelFilter.value != null && c.model_id !== modelFilter.value) return false
    if (tagFilter.value.length && !tagFilter.value.some(t => (c.scenario_tags || []).includes(t))) return false
    if (q && !(c.name || '').toLowerCase().includes(q) && !(c.requirement || '').toLowerCase().includes(q)) return false
    return true
  })
})

async function load() {
  loading.value = true
  try { cases.value = (await bomCaseApi.list({ with_parts: true })).cases || [] } catch (e: any) {
    message.error(e.response?.data?.detail || '加载 BOM案例失败')
  } finally { loading.value = false }
}

// 详情表格：L6 段优先用已固化的 l6_rows 快照；KP 段拆 bom_excel_rows（3 列：类别/型号/数量）
const l6RowsOf = (c: BomCase) =>
  (c.l6_rows && c.l6_rows.length ? c.l6_rows : (c.bom_excel_rows || []).filter(r => r.category === 'L6'))
// ── L6 自动跟随 KP：GPU 电源线=GPU 总数；散热器=CPU 总数 ──
const _isGpuCableRow = (r: L6Row) => /gpu.+power|gpu.+cable|gpu.*线|电源线/i.test(r.catalogue)
const _isHeatsinkRow = (r: L6Row) => /heatsink|散热/i.test(r.catalogue)

function syncL6FromKp() {
  const rows = form.value.l6_rows
  const gpuQty = form.value.kp_lines
    .filter(l => /gpu|显卡/i.test(l.category || ''))
    .reduce((s, l) => s + (l.qty || 0), 0)
  const cpuQty = form.value.kp_lines
    .filter(l => (l.category || '').toUpperCase() === 'CPU')
    .reduce((s, l) => s + (l.qty || 0), 0)
  // GPU 电源线：>0 同步/新增；=0 移除自动行（不配卡就不留线）
  const gpuIdx = rows.findIndex(_isGpuCableRow)
  if (gpuQty > 0) {
    if (gpuIdx >= 0) rows[gpuIdx] = { ...rows[gpuIdx], qty: gpuQty }
    else rows.push({ catalogue: 'GPU power cable', description: '', qty: gpuQty })
  } else if (gpuIdx >= 0) {
    rows.splice(gpuIdx, 1)
  }
  // 散热器：>0 同步/新增（=0 不动，避免误删用户行）
  if (cpuQty > 0) {
    const idx = rows.findIndex(_isHeatsinkRow)
    if (idx >= 0) rows[idx] = { ...rows[idx], qty: cpuQty }
    else rows.push({ catalogue: 'Heatsink', description: '', qty: cpuQty })
  }
}
watch(() => form.value.kp_lines, syncL6FromKp, { deep: true })

// ── 编辑表单 ──
function openNew() {
  editing.value = null
  form.value = {
    name: '', scenario_tags: [],
    model_id: null, base_config_id: null, bom_template_id: null,
    requirement: '',
    l6_config_desc: '',
    kp_lines: [{ part_id: null, qty: 1, hint: '' }],
    l6_rows: [],
    notes: '',
    enabled: true,
  }
  drawerOpen.value = true
}

function openEdit(c: BomCase) {
  editing.value = c
  form.value = {
    name: c.name,
    scenario_tags: [...(c.scenario_tags || [])],
    model_id: c.model_id,
    base_config_id: c.base_config_id,
    bom_template_id: c.bom_template_id,
    requirement: c.requirement || '',
    l6_config_desc: c.l6_config_desc || '',
    kp_lines: (c.kp_lines || []).map(l => ({ part_id: l.part_id, qty: l.qty, hint: l.hint || '', category: l.category || '' })),
    l6_rows: (c.l6_rows && c.l6_rows.length
      ? c.l6_rows
      : (c.bom_excel_rows || []).filter(r => r.category === 'L6')
    ).map(r => ({ catalogue: r.catalogue, description: r.description || '', qty: r.qty })),
    notes: c.notes || '',
    enabled: c.enabled,
  }
  // 预载已有行的料号选项，避免下拉裸显示 part_id（如 114）
  form.value.kp_lines.forEach(l => {
    const cid = catIdOf(l.category || '')
    if (cid) loadParts(cid)
  })
  drawerOpen.value = true
}

// ── 料号目录 ──
async function loadCategories() {
  try { cats.value = await kpCatalogApi.categories() } catch { /* 静默 */ }
}
async function loadParts(categoryId: number) {
  if (partsByCat.value[categoryId]) return
  try { partsByCat.value[categoryId] = await kpCatalogApi.parts(categoryId) } catch { /* 静默 */ }
}
function catIdOf(name: string): number | undefined {
  return cats.value.find(c => c.name === name)?.id
}
function onLineCategory(line: BomKpLine, catName: string) {
  line.part_id = null
  line.category = catName
  const id = catIdOf(catName)
  if (id) loadParts(id)
}
function lineParts(line: BomKpLine): KpPart[] {
  const id = catIdOf(line.category || '')
  return id ? (partsByCat.value[id] || []) : []
}
function addLine() { form.value.kp_lines.push({ part_id: null, qty: 1, hint: '' }) }
function removeLine(i: number) { form.value.kp_lines.splice(i, 1) }

// ── L6 行编辑 ──
function addL6Row() { form.value.l6_rows.push({ catalogue: '', description: '', qty: 1 }) }
async function reloadL6FromTemplate() {
  if (!form.value.base_config_id || !form.value.bom_template_id) { form.value.l6_rows = []; return }
  try {
    const res = await bomCaseApi.l6Preview({
      base_config_id: form.value.base_config_id,
      bom_template_id: form.value.bom_template_id,
      kp_lines: form.value.kp_lines,
    })
    form.value.l6_rows = (res.rows || []).map(r => ({ catalogue: r.catalogue, description: r.description || '', qty: r.qty }))
    syncL6FromKp()
  } catch { /* 静默 */ }
}
function onBaseConfigChange() { reloadL6FromTemplate() }
function onTemplateChange() { reloadL6FromTemplate() }

const baseConfigOptions = computed(() => {
  const list = form.value.model_id
    ? baseConfigs.value.filter(b => b.model_id === form.value.model_id)
    : baseConfigs.value
  return list.map(b => ({
    value: b.id,
    label: `${b.name}（${b.series || ''} ${b.form || ''} ${b.bays ? b.bays + '盘位' : ''}）`,
  }))
})

async function save() {
  if (!form.value.name.trim()) { message.warning('请填写案例名称'); return }
  if (!form.value.requirement.trim()) { message.warning('请填写原始需求（重放/检索依赖）'); return }
  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      scenario_tags: form.value.scenario_tags,
      model_id: form.value.model_id,
      base_config_id: form.value.base_config_id,
      bom_template_id: form.value.bom_template_id,
      requirement: form.value.requirement || undefined,
      l6_config_desc: form.value.l6_config_desc || undefined,
      kp_lines: form.value.kp_lines,
      l6_rows: form.value.l6_rows,
      notes: form.value.notes || undefined,
      enabled: form.value.enabled,
    }
    if (editing.value) {
      await bomCaseApi.update(editing.value.case_key, payload)
      message.success('已保存')
    } else {
      await bomCaseApi.create(payload)
      message.success('已创建 BOM案例')
    }
    drawerOpen.value = false
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

function remove(c: BomCase) {
  Modal.confirm({
    title: '删除该 BOM案例？',
    content: `「${c.name}」将被删除，不可恢复。`,
    okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      try { await bomCaseApi.remove(c.case_key); message.success('已删除'); await load() }
      catch (e: any) { message.error(e.response?.data?.detail || '删除失败') }
    },
  })
}

async function loadL6Refs() {
  try {
    const [m, b, t] = await Promise.all([catalogApi.listModels(), baseConfigApi.list(), bomTemplateApi.list()])
    models.value = m.models || []
    baseConfigs.value = b.configs || []
    templates.value = t.templates || []
  } catch { /* L6 引用加载失败不阻塞 */ }
}

onMounted(async () => { await loadCategories(); await loadL6Refs(); await load() })
</script>

<template>
  <div class="bc-lib">
    <!-- 左：分类（系列 / 平台 / 机型） -->
    <aside class="bc-cats">
      <div class="bc-cat-group">
        <div class="bc-cat-title">系列</div>
        <div class="bc-cat-row" :class="{ active: serverTypeFilter === null }" @click="serverTypeFilter = null">全部 <em>{{ cases.length }}</em></div>
        <div v-for="s in serverTypes" :key="'st-' + s" class="bc-cat-row" :class="{ active: serverTypeFilter === s }" @click="serverTypeFilter = s">{{ s }} <em>{{ countBy(c => c.server_type === s) }}</em></div>
      </div>
      <div class="bc-cat-group">
        <div class="bc-cat-title">平台</div>
        <div class="bc-cat-row" :class="{ active: seriesFilter === null }" @click="seriesFilter = null">全部 <em>{{ cases.length }}</em></div>
        <div v-for="s in seriesList" :key="'se-' + s" class="bc-cat-row" :class="{ active: seriesFilter === s }" @click="seriesFilter = s">{{ s }} <em>{{ countBy(c => c.series === s) }}</em></div>
      </div>
      <div class="bc-cat-group">
        <div class="bc-cat-title">机型</div>
        <div class="bc-cat-row" :class="{ active: modelFilter === null }" @click="modelFilter = null">全部 <em>{{ cases.length }}</em></div>
        <div v-for="m in modelList" :key="'m-' + m.id" class="bc-cat-row" :class="{ active: modelFilter === m.id }" @click="modelFilter = m.id">{{ m.name }} <em>{{ countBy(c => c.model_id === m.id) }}</em></div>
      </div>
    </aside>

    <!-- 右：案例列表 -->
    <section class="bc-main">
      <div class="bc-toolbar glass-light">
        <a-input v-model:value="search" placeholder="搜索案例名称 / 需求..." allow-clear class="bc-search" />
        <a-select v-model:value="tagFilter" mode="multiple" placeholder="场景标签" class="bc-tags" :options="allTags.map(t => ({ value: t, label: t }))" allow-clear />
        <a-button type="primary" @click="openNew">+ 新建 BOM案例</a-button>
      </div>

      <a-spin :spinning="loading">
        <div v-if="filtered.length" class="bc-grid">
          <div v-for="c in filtered" :key="c.case_key" class="bc-card glass is-clickable" @click="openEdit(c)">
            <div class="bc-card-top">
              <span class="bc-name">{{ c.name }}</span>
              <span class="bc-ver">v{{ c.version }}</span>
            </div>
            <div class="bc-cls">
              <a-tag v-if="c.server_type" color="purple">{{ c.server_type }}</a-tag>
              <a-tag v-if="c.series" color="cyan">{{ c.series }}</a-tag>
              <a-tag v-if="c.model_name" color="blue">{{ c.model_name }}</a-tag>
              <a-tag v-for="t in (c.scenario_tags || [])" :key="t">{{ t }}</a-tag>
            </div>
            <div class="bc-meta">
              L6 {{ l6RowsOf(c).length }} 行 · KP {{ c.kp_lines.length }} 行
            </div>
            <div class="bc-foot">
              <span class="bc-src" v-if="c.notes">{{ c.notes }}</span>
              <span class="bc-actions">
                <button class="bc-act" @click.stop="openEdit(c)">编辑</button>
                <button class="bc-act bc-act-danger" @click.stop="remove(c)">删除</button>
              </span>
            </div>
          </div>
        </div>
        <div v-else-if="!loading" class="bc-empty glass">暂无 BOM案例。</div>
      </a-spin>
    </section>

    <!-- 编辑抽屉 -->
    <a-drawer :open="drawerOpen" :title="editing ? '编辑 BOM案例' : '新建 BOM案例'" width="760px" @close="drawerOpen = false">
      <div class="bc-form">
        <div class="bc-field">
          <label>名称</label>
          <a-input v-model:value="form.name" placeholder="如：2U 通用 AMD 双路 16内存 2SATA+2NVMe" />
        </div>
        <div class="bc-field">
          <label>原始需求（必填，重放/检索依赖）</label>
          <a-textarea v-model:value="form.requirement" :auto-size="{ minRows: 2, maxRows: 6 }" placeholder="客户原始需求，如：CPU AMD 9654×2 / 内存 32G×16 / ..." />
        </div>
        <div class="bc-field">
          <label>场景标签</label>
          <a-select v-model:value="form.scenario_tags" mode="tags" placeholder="回车添加：推理 / 通用 / 信创 / 存储 ..." style="width:100%" />
        </div>

        <div class="bc-field">
          <label>分类（系列/平台由机型自动推导）</label>
          <div class="bc-inline">
            <span>机型</span>
            <a-select v-model:value="form.model_id" style="width:190px" allow-clear placeholder="选机型（分类自动带出）"
              :options="models.map(m => ({ value: m.id, label: m.name }))"
              @change="() => { form.base_config_id = null }" />
            <span>基准配置</span>
            <a-select v-model:value="form.base_config_id" style="width:220px" allow-clear placeholder="选基准配置"
              :options="baseConfigOptions"
              @change="onBaseConfigChange" />
            <span>BOM模板</span>
            <a-select v-model:value="form.bom_template_id" style="width:170px" allow-clear placeholder="选模板"
              :options="templates.map(t => ({ value: t.id, label: t.name }))"
              @change="onTemplateChange" />
          </div>
        </div>

        <div class="bc-field">
          <label>L6 Configuration Description（技术员机箱能力声明原文，重放/校验用）</label>
          <a-textarea v-model:value="form.l6_config_desc" :auto-size="{ minRows: 2, maxRows: 5 }"
            placeholder="如：ES22V3-P支持2颗AMD EPYC 9004/9005代CPU…支持12个3.5/2.5英寸SATA/SAS硬盘或者NVMe…" />
        </div>

        <div class="bc-field">
          <label>L6 配置单（可编辑；GPU 电源线 / 散热器数量自动跟随 KP 行）</label>
          <div v-for="(r, i) in form.l6_rows" :key="'l6e-' + i" class="bc-l6line">
            <a-input v-model:value="r.catalogue" placeholder="部件，如 Front backplane" style="width:190px" />
            <a-input v-model:value="r.description" placeholder="规格，如 12*3.5 SATA/SAS/NVMe" style="width:230px" />
            <a-input-number v-model:value="r.qty" :min="0" style="width:70px" />
            <a-button type="text" danger @click="form.l6_rows.splice(i, 1)">删</a-button>
          </div>
          <div class="bc-l6-actions">
            <a-button size="small" type="dashed" @click="addL6Row">+ 加 L6 行</a-button>
            <a-button size="small" @click="reloadL6FromTemplate">按 BOM 模板重载</a-button>
          </div>
        </div>

        <div class="bc-field">
          <label>KP 行（引用料号库，不复制型号文本）</label>
          <div v-for="(line, i) in form.kp_lines" :key="i" class="bc-line">
            <a-select
              :value="line.category"
              placeholder="品类"
              style="width:150px"
              :options="cats.map(c => ({ value: c.name, label: c.name }))"
              @change="(v: any) => onLineCategory(line, String(v))"
            />
            <a-select
              :value="line.part_id"
              placeholder="选料号"
              style="width:230px"
              show-search
              :options="lineParts(line).map(p => ({ value: p.id, label: p.name }))"
              @change="(v: any) => { line.part_id = v ? Number(v) : null }"
              :disabled="!line.category"
            />
            <a-input-number v-model:value="line.qty" :min="1" style="width:70px" placeholder="数量" />
            <a-input
              v-if="!line.part_id"
              v-model:value="line.hint"
              placeholder="型号子串（未关联时用于匹配）"
              style="width:150px"
            />
            <a-button type="text" danger @click="removeLine(i)">删</a-button>
          </div>
          <a-button size="small" type="dashed" block @click="addLine">+ 加一行</a-button>
        </div>

        <div class="bc-field">
          <label>说明</label>
          <a-textarea v-model:value="form.notes" :auto-size="{ minRows: 1, maxRows: 4 }" placeholder="案例说明 / 适用场景" />
        </div>


        <div class="bc-actions-bar">
          <a-button @click="drawerOpen = false">取消</a-button>
          <a-button type="primary" :loading="saving" @click="save">保存</a-button>
        </div>
      </div>
    </a-drawer>
  </div>
</template>

<style scoped>
.bc-lib { display: flex; gap: 16px; padding: 4px 2px 40px; align-items: flex-start; }
.bc-cats { width: 170px; flex-shrink: 0; position: sticky; top: 12px; display: flex; flex-direction: column; gap: 14px; }
.bc-cat-group { display: flex; flex-direction: column; gap: 2px; }
.bc-cat-title { font-size: 12px; font-weight: 700; color: var(--cpq-text-muted); margin-bottom: 4px; }
.bc-cat-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 10px; border-radius: 8px; cursor: pointer; font-size: 13px; color: var(--cpq-text-secondary); transition: background .15s; }
.bc-cat-row:hover { background: var(--cpq-overlay-b8); }
.bc-cat-row.active { background: var(--cpq-color-primary-soft, rgba(64,128,255,.14)); color: var(--cpq-accent-primary); font-weight: 600; }
.bc-cat-row em { font-style: normal; font-size: 11px; color: var(--cpq-text-disabled); }
.bc-cat-row.active em { color: var(--cpq-accent-primary); }
.bc-main { flex: 1; min-width: 0; }
.bc-toolbar { display: flex; gap: 10px; align-items: center; padding: 12px 16px; border-radius: 12px; margin-bottom: 16px; }
.bc-search { width: 240px; }
.bc-tags { min-width: 220px; }
.bc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.bc-card { padding: 16px; border-radius: 12px; display: flex; flex-direction: column; gap: 8px; }
.bc-card.is-clickable { cursor: pointer; transition: border-color .2s; }
.bc-card.is-clickable:hover { border-color: var(--cpq-accent-primary); }
.bc-card-top { display: flex; justify-content: space-between; align-items: baseline; }
.bc-name { font-weight: 600; font-size: 14px; color: var(--cpq-text-primary); }
.bc-ver { font-size: 12px; color: var(--cpq-text-muted); }
.bc-cls { display: flex; flex-wrap: wrap; gap: 4px; }
.bc-meta { font-size: 12px; color: var(--cpq-text-muted); }
.bc-foot { display: flex; justify-content: space-between; align-items: center; margin-top: auto; }
.bc-src { font-size: 11px; color: var(--cpq-text-disabled); max-width: 55%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bc-actions { display: flex; gap: 8px; }
.bc-act { background: none; border: none; color: var(--cpq-accent-primary); cursor: pointer; font-size: 12px; }
.bc-act-danger { color: var(--cpq-color-danger); }
.bc-empty { padding: 40px; text-align: center; color: var(--cpq-text-muted); border-radius: 12px; }
.bc-form { display: flex; flex-direction: column; gap: 16px; }
.bc-field { display: flex; flex-direction: column; gap: 6px; }
.bc-field > label { font-size: 13px; font-weight: 600; color: var(--cpq-text-secondary); }
.bc-line { display: flex; gap: 6px; align-items: center; }
.bc-l6line { display: flex; gap: 6px; align-items: center; }
.bc-l6-actions { display: flex; gap: 8px; margin-top: 6px; }
.bc-inline { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 13px; color: var(--cpq-text-secondary); }
.bc-actions-bar { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }
</style>
