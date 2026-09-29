<template>
  <div class="atc-root">
    <!-- ───────────── 模板库 ───────────── -->
    <template v-if="view === 'library'">
      <div class="atc-lib-head">
        <div>
          <div class="atc-lib-title">产出物模板</div>
          <div class="atc-hint">模板 = 确定性格式契约（区块 + 图表资产引用）；AI 只填内容，渲染走 HTML→PDF 管线。工作流输出节点可选模板替代随机排版。</div>
        </div>
        <div class="atc-chips">
          <button class="atc-chip active" type="button">PDF</button>
          <button class="atc-chip" type="button" disabled title="下期开放">Excel</button>
          <button class="atc-chip" type="button" disabled title="下期开放">PPT</button>
        </div>
      </div>

      <a-spin :spinning="loading">
        <div class="atc-grid">
          <div v-for="tpl in templates" :key="tpl.id" class="atc-card" @click="openEditor(tpl)">
            <div class="atc-card-top">
              <span class="atc-fmt">PDF</span>
              <span class="atc-card-name">{{ tpl.name }}</span>
              <a-popconfirm title="删除该模板？输出节点引用将回退默认渲染。" ok-text="删除" cancel-text="取消" @confirm.stop="removeTemplate(tpl)">
                <a-button class="atc-card-del" type="text" size="small" danger @click.stop><DeleteOutlined /></a-button>
              </a-popconfirm>
            </div>
            <div class="atc-card-key">{{ tpl.key }}</div>
            <div class="atc-card-desc">{{ tpl.description || '（无描述）' }}</div>
            <div class="atc-card-meta">
              <span>{{ blockSummary(tpl) }}</span>
              <span>{{ (tpl.updated_at || '').slice(0, 10) }}</span>
            </div>
          </div>
          <button class="atc-card atc-card-add" type="button" @click="createTemplate">
            <span class="atc-add-plus">＋</span>
            <span>新建 PDF 模板</span>
          </button>
        </div>
      </a-spin>
    </template>

    <!-- ───────────── PDF 编辑器（三栏） ───────────── -->
    <template v-else>
      <div class="atc-ed-head">
        <a-button size="small" @click="backToLibrary">← 模板库</a-button>
        <a-input v-model:value="editing.name" class="atc-ed-name" placeholder="模板名称" />
        <a-input v-model:value="editing.key" class="atc-ed-key" placeholder="key（唯一标识）" :disabled="!!editing.id" />
        <div class="atc-ed-spacer" />
        <a-button :loading="pdfLoading" @click="exportSamplePdf">导出样例 PDF</a-button>
        <a-button type="primary" :loading="saving" @click="save">保存</a-button>
      </div>

      <div class="atc-ed-body">
        <!-- 左栏：结构 / 图表资产 -->
        <aside class="atc-left">
          <a-tabs v-model:activeKey="leftTab" size="small" class="atc-left-tabs">
            <a-tab-pane key="structure" tab="结构">
              <div class="atc-block-list">
                <div
                  v-for="(blk, i) in editing.blocks"
                  :key="blk.id || i"
                  class="atc-block-item"
                  :class="{ selected: selectedIdx === i, 'drag-target': dragOverIdx === i && dragFromIdx !== i }"
                  :draggable="dragUid === blk.id"
                  @click="selectedIdx = i"
                  @dragstart="onDragStart(i, $event)"
                  @dragover="onDragOver(i, $event)"
                  @dragleave="dragOverIdx = -1"
                  @drop.prevent="onDrop(i)"
                  @dragend="onDragEnd"
                >
                  <span
                    class="atc-drag"
                    title="拖拽排序"
                    @mousedown="dragUid = (blk.id as string)"
                    @mouseup="dragUid = null"
                  >⠿</span>
                  <span class="atc-block-ico">{{ blockIcon(blk.type) }}</span>
                  <span class="atc-block-name">{{ blockLabel(blk) }}</span>
                  <span class="atc-block-ops">
                    <button type="button" class="del" @click.stop="removeBlock(i)">✕</button>
                  </span>
                </div>
              </div>
              <div class="atc-add-row">
                <button v-for="t in BLOCK_TYPES" :key="t.type" type="button" class="atc-add-btn" @click="addBlock(t.type)">
                  {{ t.icon }} {{ t.label }}
                </button>
              </div>
            </a-tab-pane>
            <a-tab-pane key="assets" tab="图表资产">
              <div class="atc-hint atc-left-hint">引用系统已有图表，与来源页同源；来源页改口径，报告自动跟。</div>
              <div
                v-for="asset in chartAssets"
                :key="asset.id"
                class="atc-asset-card"
                :class="{ used: assetUsed(asset.id) }"
                @click="addAssetBlock(asset)"
              >
                <div class="atc-asset-top">
                  <span class="atc-asset-kind" :class="`k-${asset.kind}`">{{ asset.kind === 'kpi' ? '指标' : asset.kind === 'table' ? '表格' : '图表' }}</span>
                  <span class="atc-asset-name">{{ asset.name }}</span>
                  <span v-if="assetUsed(asset.id)" class="atc-asset-ref">已引用</span>
                </div>
                <div class="atc-asset-desc">{{ asset.desc }}</div>
                <div class="atc-asset-src">来源：{{ asset.source_page }}</div>
              </div>
            </a-tab-pane>
          </a-tabs>
        </aside>

        <!-- 中栏：A4 纸预览（点击区块反向选中；高度随内容自适应解除单页裁切） -->
        <main class="atc-center">
          <a-spin :spinning="previewing" wrapper-class-name="atc-paper-spin">
            <div class="atc-paper-wrap">
              <iframe
                v-if="previewHtml"
                ref="paperFrame"
                class="atc-paper-frame"
                :style="{ height: previewH + 'px' }"
                :srcdoc="previewHtml"
                title="模板预览"
                @load="sendHighlight"
              />
              <div v-else class="atc-paper-empty">区块为空或预览加载中…</div>
            </div>
          </a-spin>
        </main>

        <!-- 右栏：属性 + 数据契约 -->
        <aside class="atc-right">
          <div class="atc-sec-title">属性</div>
          <template v-if="selectedBlock">
            <div class="atc-prop-row">
              <span class="atc-prop-label">类型</span>
              <span>{{ typeLabel(selectedBlock.type) }}</span>
            </div>
            <template v-if="selectedBlock.type === 'title'">
              <div class="atc-prop-row">
                <span class="atc-prop-label">主标题</span>
                <a-input v-model:value="selectedBlock.title" size="small" placeholder="留空 = 跟随报告名" />
              </div>
              <div class="atc-prop-row">
                <span class="atc-prop-label">副题</span>
                <a-input v-model:value="selectedBlock.subtitle" size="small" placeholder="留空 = 跟随文档卡副题" />
              </div>
              <div class="atc-prop-row">
                <span class="atc-prop-label">品牌名</span>
                <a-input v-model:value="selectedBlock.brand_name" size="small" placeholder="默认 CPQ PLATFORM" />
              </div>
              <div class="atc-prop-row">
                <span class="atc-prop-label">品牌副标</span>
                <a-input v-model:value="selectedBlock.brand_tag" size="small" placeholder="留空 = 跟随生成方" />
              </div>
            </template>
            <div v-else class="atc-prop-row">
              <span class="atc-prop-label">区块标题</span>
              <a-input v-model:value="selectedBlock.title" size="small" placeholder="（可选）区块小标题" />
            </div>
            <div v-if="selectedBlock.type !== 'title'" class="atc-prop-row">
              <span class="atc-prop-label">宽度</span>
              <div class="atc-span-chips">
                <button
                  v-for="s in SPAN_OPTS"
                  :key="s.v"
                  type="button"
                  class="atc-span-chip"
                  :class="{ active: spanOf(selectedBlock!) === s.v }"
                  @click="setSpan(selectedBlock!, s.v)"
                >{{ s.label }}</button>
              </div>
            </div>
            <template v-if="selectedBlock.type === 'text'">
              <div class="atc-prop-row">
                <span class="atc-prop-label">内容来源</span>
                <a-select v-model:value="selectedBlock.source" size="small" style="width: 100%">
                  <a-select-option value="answer">AI 答复（整段 markdown）</a-select-option>
                  <a-select-option value="payload">payload_map 字段</a-select-option>
                  <a-select-option value="literal">静态文案（模板自写）</a-select-option>
                </a-select>
              </div>
              <div v-if="selectedBlock.source === 'payload'" class="atc-prop-row">
                <span class="atc-prop-label">字段名</span>
                <a-input v-model:value="selectedBlock.key" size="small" placeholder="如 summary" />
              </div>
              <div v-if="selectedBlock.source === 'literal'" class="atc-prop-row atc-prop-stack">
                <span class="atc-prop-label">文案内容</span>
                <a-textarea
                  v-model:value="selectedBlock.text"
                  :rows="6"
                  placeholder="支持 markdown 子集：**加粗**、- 列表、1. 编号、表格"
                />
              </div>
            </template>
            <template v-if="['kpi', 'chart', 'table'].includes(selectedBlock.type)">
              <div class="atc-prop-row">
                <span class="atc-prop-label">图表资产</span>
                <a-select
                  :value="selectedBlock.asset"
                  size="small"
                  style="width: 100%"
                  placeholder="选择资产"
                  @change="(v: any) => (selectedBlock!.asset = v)"
                >
                  <a-select-option v-for="a in assetsFor(selectedBlock.type)" :key="a.id" :value="a.id">
                    {{ a.name }}（{{ a.source_page }}）
                  </a-select-option>
                </a-select>
              </div>
              <div v-for="spec in assetParamSpecs(selectedBlock!)" :key="spec.key" class="atc-prop-row">
                <span class="atc-prop-label">{{ spec.label }}</span>
                <a-input-number
                  :value="paramValue(selectedBlock!, spec.key)"
                  size="small"
                  :min="spec.min"
                  :max="spec.max"
                  :step="spec.step || 1"
                  :placeholder="`默认 ${spec.default}${spec.unit || ''}`"
                  style="width: 100%"
                  @change="(v: any) => setParam(selectedBlock!, spec.key, v)"
                />
              </div>
            </template>
            <template v-if="selectedBlock.type === 'kpi' && kpiCatalog(selectedBlock!).length">
              <div class="atc-prop-row atc-prop-stack">
                <span class="atc-prop-label">指标构成</span>
                <div class="atc-kpi-pick">
                  <label v-for="m in kpiCatalog(selectedBlock!)" :key="m.key" class="atc-kpi-check">
                    <input
                      type="checkbox"
                      :checked="kpiPicked(selectedBlock!, m.key)"
                      @change="(e: any) => toggleKpi(selectedBlock!, m.key, e.target.checked)"
                    />
                    <span>{{ m.label }}</span>
                  </label>
                </div>
                <div v-for="(m, mi) in selectedBlock.metrics" :key="'row-' + m.key" class="atc-kpi-row">
                  <span class="atc-kpi-row-name">{{ kpiName(selectedBlock!, m.key) }}</span>
                  <a-input
                    :value="m.label"
                    size="small"
                    :placeholder="kpiName(selectedBlock!, m.key)"
                    @change="(e: any) => setKpiLabel(selectedBlock!, m.key, e.target.value)"
                  />
                  <button type="button" class="atc-kpi-move" :disabled="mi === 0" @click="moveKpi(selectedBlock!, mi, -1)">↑</button>
                  <button type="button" class="atc-kpi-move" :disabled="mi === (selectedBlock!.metrics || []).length - 1" @click="moveKpi(selectedBlock!, mi, 1)">↓</button>
                </div>
              </div>
            </template>
            <div v-if="selectedBlock.type === 'chart'" class="atc-prop-row">
              <span class="atc-prop-label">高度(px)</span>
              <a-input-number v-model:value="selectedBlock.height" size="small" :min="160" :max="420" :step="20" style="width: 100%" />
            </div>
          </template>
          <div v-else class="atc-hint">选中左侧区块编辑属性。</div>

          <div class="atc-sec-title" style="margin-top: 18px">数据契约</div>
          <div class="atc-hint atc-ct-hint">点击契约行定位到对应区块</div>
          <div class="atc-contract">
            <div
              v-for="(row, i) in contractRows"
              :key="i"
              class="atc-ct-row"
              :class="{ active: row.blockIdx === selectedIdx }"
              role="button"
              tabindex="0"
              @click="locateBlock(row.blockIdx)"
              @keydown.enter="locateBlock(row.blockIdx)"
            >
              <span class="atc-ct-dot" :class="row.who" />
              <span class="atc-ct-sym">{{ row.sym }}</span>
              <span class="atc-ct-note">{{ row.note }}</span>
            </div>
          </div>

          <div class="atc-sec-title" style="margin-top: 18px">渲染配方</div>
          <div class="atc-hint">区块序列 + 图表资产（服务端取数）→ HTML（A4 版式）→ Playwright 打印 PDF。文本块内容由输出节点的 AI 答复或 payload_map 提供，模板层零 AI。</div>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined } from '@ant-design/icons-vue'
import axios from 'axios'
import {
  artifactTemplateApi,
  type ArtifactBlock,
  type ArtifactTemplate,
  type ChartAssetMeta,
} from '@/api/artifactTemplates'

const BLOCK_TYPES = [
  { type: 'title', label: '标题', icon: 'T' },
  { type: 'text', label: '文本', icon: '¶' },
  { type: 'kpi', label: '指标', icon: '◧' },
  { type: 'chart', label: '图表', icon: '▲' },
  { type: 'table', label: '表格', icon: '▦' },
] as const

const view = ref<'library' | 'editor'>('library')
const loading = ref(false)
const templates = ref<ArtifactTemplate[]>([])
const chartAssets = ref<ChartAssetMeta[]>([])

const leftTab = ref<'structure' | 'assets'>('structure')
const selectedIdx = ref(-1)
const saving = ref(false)
const pdfLoading = ref(false)
const previewing = ref(false)
const previewHtml = ref('')

let previewTimer: ReturnType<typeof setTimeout> | null = null
let previewSeq = 0

const editing = reactive({
  id: 0,
  key: '',
  name: '',
  description: '',
  blocks: [] as ArtifactBlock[],
})

const selectedBlock = computed(() =>
  selectedIdx.value >= 0 && selectedIdx.value < editing.blocks.length ? editing.blocks[selectedIdx.value] : null,
)

// 预览 iframe 反选（previewHtml 由后端 interactive 模式注入 postMessage 协议）
const paperFrame = ref<HTMLIFrameElement | null>(null)
const previewH = ref(1123)

function sendHighlight() {
  paperFrame.value?.contentWindow?.postMessage({ type: 'atc-highlight', idx: selectedIdx.value }, '*')
}

function onPreviewMessage(ev: MessageEvent) {
  const d = ev.data
  if (!d || typeof d !== 'object') return
  if (d.type === 'atc-select' && typeof d.idx === 'number' && d.idx >= 0 && d.idx < editing.blocks.length) {
    selectedIdx.value = d.idx
  } else if (d.type === 'atc-height' && typeof d.h === 'number') {
    previewH.value = Math.max(1123, Math.min(20000, Math.ceil(d.h)))
  }
}

watch(selectedIdx, () => sendHighlight())

// ───────────── 库 ─────────────

function blockSummary(tpl: ArtifactTemplate): string {
  const charts = tpl.blocks.filter((b) => b.type === 'chart').length
  const tables = tpl.blocks.filter((b) => b.type === 'table').length
  return `${tpl.blocks.length} 区块 · ${charts} 图 · ${tables} 表`
}

async function loadTemplates() {
  loading.value = true
  try {
    templates.value = await artifactTemplateApi.list()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '模板列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadAssets() {
  try {
    chartAssets.value = await artifactTemplateApi.listChartAssets()
  } catch {
    /* 资产加载失败不阻塞编辑器（图表块仍可保存） */
  }
}

function openEditor(tpl: ArtifactTemplate) {
  editing.id = tpl.id
  editing.key = tpl.key
  editing.name = tpl.name
  editing.description = tpl.description
  editing.blocks = JSON.parse(JSON.stringify(tpl.blocks || [])).map((b: ArtifactBlock) => ({ ...b, id: b.id || uid() }))
  selectedIdx.value = -1
  leftTab.value = 'structure'
  view.value = 'editor'
  schedulePreview()
}

function createTemplate() {
  editing.id = 0
  editing.key = ''
  editing.name = ''
  editing.description = ''
  editing.blocks = [
    { id: uid(), type: 'title' },
    { id: uid(), type: 'kpi', asset: 'cockpit.kpi', title: '核心指标' },
    { id: uid(), type: 'text', source: 'answer', title: 'AI 分析结论' },
  ]
  selectedIdx.value = -1
  view.value = 'editor'
  schedulePreview()
}

function backToLibrary() {
  view.value = 'library'
  loadTemplates()
}

async function removeTemplate(tpl: ArtifactTemplate) {
  try {
    await artifactTemplateApi.remove(tpl.id)
    message.success('已删除')
    await loadTemplates()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

// ───────────── 区块编辑 ─────────────

function uid(): string {
  return Math.random().toString(36).slice(2, 10)
}

function blockIcon(type: string): string {
  return BLOCK_TYPES.find((t) => t.type === type)?.icon || '·'
}

function blockLabel(blk: ArtifactBlock): string {
  if (blk.type === 'title') return '报告标题'
  if (blk.type === 'text') return blk.title || (blk.source === 'payload' ? `payload.${blk.key || '?'}` : 'AI 答复')
  const asset = chartAssets.value.find((a) => a.id === blk.asset)
  return blk.title || asset?.name || typeLabel(blk.type)
}

function typeLabel(type: string): string {
  return BLOCK_TYPES.find((t) => t.type === type)?.label || type
}

function addBlock(type: string) {
  const blk: ArtifactBlock = { id: uid(), type: type as ArtifactBlock['type'] }
  if (type === 'text') blk.source = 'answer'
  if (type === 'kpi') blk.asset = 'cockpit.kpi'
  if (type === 'chart') blk.asset = chartAssets.value.find((a) => a.kind === 'chart')?.id || 'cockpit.trend'
  if (type === 'table') blk.asset = 'cockpit.top_opps'
  editing.blocks.push(blk)
  selectedIdx.value = editing.blocks.length - 1
}

function addAssetBlock(asset: ChartAssetMeta) {
  const blk: ArtifactBlock = { id: uid(), type: asset.kind as ArtifactBlock['type'], asset: asset.id }
  if (asset.kind === 'chart') blk.height = 240
  editing.blocks.push(blk)
  selectedIdx.value = editing.blocks.length - 1
  leftTab.value = 'structure'
}

function assetUsed(assetId: string): boolean {
  return editing.blocks.some((b) => b.asset === assetId)
}

function assetsFor(type: string): ChartAssetMeta[] {
  const kind = type === 'kpi' ? 'kpi' : type === 'table' ? 'table' : 'chart'
  return chartAssets.value.filter((a) => a.kind === kind)
}

// ── 资产参数（后端 params_schema 驱动；清空=回落 fetch 默认值） ──

function assetParamSpecs(blk: ArtifactBlock) {
  if (!blk.asset) return []
  return chartAssets.value.find((a) => a.id === blk.asset)?.params || []
}

function paramValue(blk: ArtifactBlock, key: string): number | undefined {
  const v = (blk.params || {})[key]
  if (v === undefined || v === null || v === '') return undefined
  const n = Number(v)
  return Number.isFinite(n) ? n : undefined
}

function setParam(blk: ArtifactBlock, key: string, v: number | null) {
  if (v === null || v === undefined) {
    if (blk.params) delete blk.params[key]
    return
  }
  if (!blk.params) blk.params = {}
  blk.params[key] = v
}

// ── 宽度（12 列栅格 span；同宽区块自动并排）──

const SPAN_OPTS = [
  { v: 12, label: '整行' },
  { v: 8, label: '2/3 行' },
  { v: 6, label: '半行' },
  { v: 4, label: '1/3 行' },
] as const

function spanOf(blk: ArtifactBlock): number {
  const n = Number(blk.span)
  return [4, 6, 8, 12].includes(n) ? n : 12
}

function setSpan(blk: ArtifactBlock, v: number) {
  if (v === 12) delete blk.span
  else blk.span = v
}

// ── kpi 指标构成（目录=后端资产 metrics；数组序=渲染序）──

function kpiCatalog(blk: ArtifactBlock) {
  return chartAssets.value.find((a) => a.id === blk.asset)?.metrics || []
}

function kpiName(blk: ArtifactBlock, key: string): string {
  return kpiCatalog(blk).find((m) => m.key === key)?.label || key
}

function kpiPicked(blk: ArtifactBlock, key: string): boolean {
  return (blk.metrics || []).some((m) => m.key === key)
}

function toggleKpi(blk: ArtifactBlock, key: string, checked: boolean) {
  const cur = blk.metrics || kpiCatalog(blk).map((m) => ({ key: m.key }))
  blk.metrics = checked ? [...cur, { key }] : cur.filter((m) => m.key !== key)
}

function setKpiLabel(blk: ArtifactBlock, key: string, label: string) {
  const m = (blk.metrics || []).find((x) => x.key === key)
  if (!m) return
  if (label) m.label = label
  else delete m.label
}

function moveKpi(blk: ArtifactBlock, i: number, dir: -1 | 1) {
  const arr = blk.metrics
  if (!arr) return
  const j = i + dir
  if (j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

// 选中 kpi 区块时物化指标构成（未配置=全目录），改名/排序在数组上就地生效
watch(selectedBlock, (blk) => {
  if (blk && blk.type === 'kpi' && !Array.isArray(blk.metrics) && kpiCatalog(blk).length) {
    blk.metrics = kpiCatalog(blk).map((m) => ({ key: m.key }))
  }
})

function locateBlock(idx: number) {
  if (idx < 0 || idx >= editing.blocks.length) return
  selectedIdx.value = idx
  nextTick(() => {
    document
      .querySelector(`.atc-block-list .atc-block-item:nth-child(${idx + 1})`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

function removeBlock(i: number) {
  editing.blocks.splice(i, 1)
  if (selectedIdx.value >= editing.blocks.length) selectedIdx.value = editing.blocks.length - 1
}

// ── 拖拽把手排序（原型形态：⠿ handle 触发，非整行拖拽）──
const dragUid = ref<string | null>(null)
const dragFromIdx = ref(-1)
const dragOverIdx = ref(-1)

function onDragStart(i: number, e: DragEvent) {
  dragFromIdx.value = i
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(i))
  }
}

function onDragOver(i: number, e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dragOverIdx.value = i
}

function onDrop(i: number) {
  const from = dragFromIdx.value
  if (from >= 0 && from !== i) {
    const [blk] = editing.blocks.splice(from, 1)
    editing.blocks.splice(i, 0, blk)
    selectedIdx.value = i
  }
  dragFromIdx.value = -1
  dragOverIdx.value = -1
}

function onDragEnd() {
  dragUid.value = null
  dragFromIdx.value = -1
  dragOverIdx.value = -1
}

// ───────────── 数据契约（三色语义） ─────────────

const contractRows = computed(() => {
  const rows: Array<{ who: 'ai' | 'tool' | 'sys'; sym: string; note: string; blockIdx: number }> = []
  editing.blocks.forEach((blk, i) => {
    if (blk.type === 'title') {
      rows.push({ who: 'sys', sym: 'meta.title', note: '系统变量：统计区间/生成时间（标题/副题/品牌可在属性钉固定文案）', blockIdx: i })
    } else if (blk.type === 'text') {
      if (blk.source === 'literal') rows.push({ who: 'sys', sym: 'template', note: '模板固定文案：属性里直接编辑', blockIdx: i })
      else if (blk.source === 'payload' && blk.key) rows.push({ who: 'ai', sym: `payload.${blk.key}`, note: 'AI 填充：输出节点 payload_map 字段', blockIdx: i })
      else rows.push({ who: 'ai', sym: 'answer', note: 'AI 填充：整段 markdown 答复', blockIdx: i })
    } else if (blk.asset) {
      const asset = chartAssets.value.find((a) => a.id === blk.asset)
      rows.push({ who: 'tool', sym: `{${blk.type === 'chart' ? 'chart' : blk.type === 'kpi' ? 'kpi' : 'table'}:${blk.asset}}`, note: `工具取数：${asset?.name || blk.asset}（${asset?.source_page || '系统'}）`, blockIdx: i })
    }
  })
  return rows
})

// ───────────── 预览（防抖 500ms，真实库数据） ─────────────

function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(runPreview, 500)
}

async function runPreview() {
  const seq = ++previewSeq
  previewing.value = true
  try {
    const html = await artifactTemplateApi.preview({
      key: editing.key || 'preview',
      name: editing.name,
      format: 'pdf',
      blocks: editing.blocks,
    })
    if (seq === previewSeq) previewHtml.value = html
  } catch (e: any) {
    if (seq === previewSeq) message.error(e?.response?.data?.detail || '预览失败')
  } finally {
    if (seq === previewSeq) previewing.value = false
  }
}

watch(
  () => [editing.blocks, editing.name],
  () => {
    if (view.value === 'editor') schedulePreview()
  },
  { deep: true },
)

// ───────────── 保存 / 样例 PDF ─────────────

async function save() {
  const key = editing.key.trim()
  if (!key) {
    message.warning('请填写模板 key')
    return
  }
  if (!/^[A-Za-z0-9_-]+$/.test(key)) {
    message.warning('key 仅限字母/数字/-/_')
    return
  }
  if (!editing.blocks.length) {
    message.warning('至少需要一个区块')
    return
  }
  saving.value = true
  try {
    const payload = {
      key,
      name: editing.name.trim() || key,
      format: 'pdf',
      description: editing.description,
      blocks: editing.blocks,
    }
    if (editing.id) await artifactTemplateApi.update(editing.id, payload)
    else {
      const created = await artifactTemplateApi.create(payload)
      editing.id = created.id
    }
    message.success('已保存')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function exportSamplePdf() {
  pdfLoading.value = true
  try {
    const res = await axios.post(
      '/api/artifact-templates/render-sample-pdf',
      {
        key: editing.key || 'sample',
        name: editing.name,
        format: 'pdf',
        description: editing.description,
        blocks: editing.blocks,
      },
      { responseType: 'blob' },
    )
    const url = URL.createObjectURL(res.data)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (e: any) {
    const detail = await blobDetail(e)
    message.error(detail || 'PDF 渲染失败')
  } finally {
    pdfLoading.value = false
  }
}

async function blobDetail(e: any): Promise<string> {
  try {
    if (e?.response?.data instanceof Blob) {
      const text = await e.response.data.text()
      return JSON.parse(text)?.detail || ''
    }
  } catch {
    /* ignore */
  }
  return ''
}

onMounted(() => {
  loadTemplates()
  loadAssets()
  window.addEventListener('message', onPreviewMessage)
})

onBeforeUnmount(() => {
  window.removeEventListener('message', onPreviewMessage)
  if (previewTimer) clearTimeout(previewTimer)
})
</script>

<style scoped>
.atc-root {
  --atc-border: #e5e7eb;
  --atc-ink: #1f2430;
  --atc-sub: #6b7280;
  --atc-blue: #1d4ed8;
  --atc-green: #16a34a;
  --atc-panel: #ffffff;
  --atc-soft: #f9fafb;
  color: var(--atc-ink);
  padding: 4px 2px;
}

/* ── 模板库 ── */
.atc-lib-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.atc-lib-title { font-size: 15px; font-weight: 700; }
.atc-hint { font-size: 12px; color: var(--atc-sub); line-height: 1.6; }
.atc-chips { display: flex; gap: 8px; flex-shrink: 0; }
.atc-chip {
  border: 1px solid var(--atc-border);
  background: var(--atc-panel);
  color: var(--atc-sub);
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 12px;
  cursor: pointer;
}
.atc-chip.active { border-color: var(--atc-blue); color: var(--atc-blue); font-weight: 600; }
.atc-chip:disabled { opacity: 0.45; cursor: not-allowed; }

.atc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 14px;
}
.atc-card {
  border: 1px solid var(--atc-border);
  border-radius: 14px;
  background: var(--atc-panel);
  padding: 16px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 130px;
  text-align: left;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.atc-card:hover { border-color: var(--atc-blue); box-shadow: 0 4px 16px rgba(29, 78, 216, 0.08); }
.atc-card-top { display: flex; align-items: center; gap: 8px; }
.atc-fmt {
  font-size: 10px;
  font-weight: 700;
  color: var(--atc-blue);
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 1px 5px;
}
.atc-card-name { font-weight: 700; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.atc-card-del { opacity: 0; }
.atc-card:hover .atc-card-del { opacity: 1; }
.atc-card-key { font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: var(--atc-sub); }
.atc-card-desc {
  font-size: 12px; color: var(--atc-sub); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.atc-card-meta {
  margin-top: auto;
  display: flex; justify-content: space-between;
  font-size: 11px; color: var(--atc-sub);
}
.atc-card-add {
  border-style: dashed;
  align-items: center;
  justify-content: center;
  color: var(--atc-sub);
  background: transparent;
  gap: 8px;
}
.atc-card-add:hover { color: var(--atc-blue); }
.atc-add-plus { font-size: 22px; line-height: 1; }

/* ── 编辑器 ── */
.atc-ed-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.atc-ed-name { width: 220px; }
.atc-ed-key { width: 220px; font-family: ui-monospace, Consolas, monospace; }
.atc-ed-spacer { flex: 1; }

.atc-ed-body {
  display: grid;
  grid-template-columns: 264px 1fr 268px;
  gap: 14px;
  align-items: stretch;
}
.atc-left, .atc-right {
  border: 1px solid var(--atc-border);
  border-radius: 14px;
  background: var(--atc-panel);
  padding: 12px;
  overflow-y: auto;
  max-height: calc(88vh - 140px);
}
.atc-left-tabs :deep(.ant-tabs-nav) { margin-bottom: 10px; }
.atc-left-hint { margin-bottom: 10px; }

.atc-block-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.atc-block-item {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--atc-border);
  border-radius: 10px;
  padding: 7px 10px;
  cursor: pointer;
  font-size: 12px;
}
.atc-block-item.selected { border-color: var(--atc-blue); background: rgba(29, 78, 216, 0.05); }
.atc-block-item.drag-target { border-color: var(--atc-blue); border-style: dashed; }
.atc-drag {
  cursor: grab;
  color: #9ca3af;
  font-size: 14px;
  line-height: 1;
  padding: 2px 2px 2px 0;
  user-select: none;
}
.atc-drag:hover { color: var(--atc-blue); }
.atc-block-item[draggable='true'] { cursor: grabbing; opacity: 0.75; }
.atc-block-ico { color: var(--atc-blue); font-weight: 700; width: 14px; text-align: center; }
.atc-block-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.atc-block-ops { display: none; gap: 2px; }
.atc-block-item:hover .atc-block-ops { display: flex; }
.atc-block-ops button {
  border: 0; background: transparent; cursor: pointer; color: var(--atc-sub);
  width: 18px; height: 18px; border-radius: 4px; font-size: 11px;
}
.atc-block-ops button:hover { background: var(--atc-soft); color: var(--atc-ink); }
.atc-block-ops button.del:hover { color: #dc2626; }
.atc-block-ops button:disabled { opacity: 0.3; cursor: default; }

.atc-add-row { display: flex; flex-wrap: wrap; gap: 6px; }
.atc-add-btn {
  border: 1px dashed var(--atc-border);
  background: transparent;
  border-radius: 8px;
  padding: 5px 9px;
  font-size: 12px;
  color: var(--atc-sub);
  cursor: pointer;
}
.atc-add-btn:hover { color: var(--atc-blue); border-color: var(--atc-blue); }

.atc-asset-card {
  border: 1px solid var(--atc-border);
  border-radius: 12px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  font-size: 12px;
}
.atc-asset-card:hover { border-color: var(--atc-blue); }
.atc-asset-card.used { border-color: var(--atc-green); }
.atc-asset-top { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.atc-asset-kind {
  font-size: 10px;
  border-radius: 4px;
  padding: 1px 5px;
  font-weight: 600;
  color: var(--atc-blue);
  background: rgba(29, 78, 216, 0.08);
}
.atc-asset-kind.k-kpi { color: #d97706; background: rgba(217, 119, 6, 0.1); }
.atc-asset-kind.k-table { color: #7c3aed; background: rgba(124, 58, 237, 0.1); }
.atc-asset-name { font-weight: 600; flex: 1; }
.atc-asset-ref { font-size: 10px; color: var(--atc-green); }
.atc-asset-desc { color: var(--atc-sub); line-height: 1.5; margin-bottom: 3px; }
.atc-asset-src { font-size: 11px; color: var(--atc-sub); }

/* 中栏 A4 纸 */
.atc-center { overflow: auto; max-height: calc(88vh - 140px); }
.atc-paper-spin { display: block; width: 100%; }
.atc-paper-wrap {
  width: 794px;
  min-height: 1123px;
  margin: 0 auto;
  background: #fff;
  box-shadow: 0 6px 30px rgba(15, 23, 42, 0.12);
  border-radius: 2px;
  overflow: hidden;
}
.atc-paper-frame { width: 794px; border: 0; display: block; }
.atc-paper-empty {
  height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--atc-sub);
  font-size: 13px;
}

/* 右栏 */
.atc-sec-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--atc-ink);
  padding-left: 8px;
  border-left: 3px solid var(--atc-blue);
  margin-bottom: 10px;
}
.atc-prop-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; }
.atc-prop-label { width: 58px; color: var(--atc-sub); flex-shrink: 0; }
.atc-contract { display: flex; flex-direction: column; gap: 6px; }
.atc-ct-hint { margin-bottom: 8px; }
.atc-ct-row {
  display: flex; align-items: center; gap: 8px; font-size: 12px;
  cursor: pointer; border-radius: 6px; padding: 2px 4px; margin: 0 -4px;
  transition: background 0.15s;
}
.atc-ct-row:hover { background: var(--atc-soft); }
.atc-ct-row.active { background: rgba(29, 78, 216, 0.08); }
.atc-ct-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.atc-ct-dot.ai { background: var(--atc-green); }
.atc-ct-dot.tool { background: var(--atc-blue); }
.atc-ct-dot.sys { background: #9ca3af; }
.atc-ct-sym {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
  color: var(--atc-ink);
  background: var(--atc-soft);
  border-radius: 4px;
  padding: 1px 6px;
}
.atc-ct-note { color: var(--atc-sub); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 宽度 chips / kpi 指标构成 ── */
.atc-span-chips { display: flex; gap: 6px; }
.atc-span-chip {
  flex: 1; padding: 3px 0; font-size: 11px; cursor: pointer;
  border: 1px solid var(--atc-border); border-radius: 4px;
  background: transparent; color: var(--atc-sub);
}
.atc-span-chip.active { border-color: var(--atc-blue); color: var(--atc-blue); font-weight: 600; background: rgba(29, 78, 216, 0.06); }
.atc-prop-stack { flex-direction: column; align-items: stretch; gap: 6px; }
.atc-kpi-pick { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.atc-kpi-check { display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; cursor: pointer; color: var(--atc-ink); }
.atc-kpi-check input { accent-color: var(--atc-blue); }
.atc-kpi-row { display: flex; align-items: center; gap: 5px; }
.atc-kpi-row-name { flex: 0 0 76px; font-size: 11px; color: var(--atc-sub); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.atc-kpi-move {
  flex: 0 0 20px; height: 22px; font-size: 11px; cursor: pointer; line-height: 1;
  border: 1px solid var(--atc-border); border-radius: 4px; background: transparent; color: var(--atc-sub);
}
.atc-kpi-move:disabled { opacity: 0.35; cursor: default; }

[data-theme='dark'] .atc-root {
  --atc-border: rgba(255, 255, 255, 0.12);
  --atc-ink: #e5e7eb;
  --atc-sub: #9ca3af;
  --atc-panel: rgba(255, 255, 255, 0.04);
  --atc-soft: rgba(255, 255, 255, 0.08);
}
[data-theme='dark'] .atc-paper-wrap { box-shadow: 0 6px 30px rgba(0, 0, 0, 0.4); }
</style>
