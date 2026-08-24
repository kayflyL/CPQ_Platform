<script setup lang="ts">
/**
 * 服务器图纸配置（服务器管理子页 /servers/drawing/:modelId）
 * 流程：选机型 → 上传 SVG（服务端清洗）→ 标注区域 / 编辑图层 → 保存。
 * 图层能力：解析 SVG 图层树，支持显隐/锁定/重命名（含命名模板）/透明度/排序，
 * 画布上点选元素移动、缩放、旋转、删除、复制；替换图纸带绑定报告与坐标迁移，可回退。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { UploadOutlined, SaveOutlined, RollbackOutlined, SwapOutlined, HistoryOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { catalogApi, partsApi, type PartMajorCategory, type ServerModel } from '@/api/serverConfig'
import { serverDrawingApi, type DrawingRegion, type DrawingLayerMeta, type DrawingVersion, type DrawingViewBox, type DrawingViewType } from '@/api/serverDrawing'
import { ServerAnatomyEditor } from '@/components/server-visualization'
import SvgLayerPanel from '@/components/server-visualization/SvgLayerPanel.vue'
import { parseSvgLayers, templateName, type SvgLayerNode } from '@/utils/svgLayers'

const models = ref<ServerModel[]>([])
// 区域类型 = 料号库大类（id→名称），徽标/下拉显示用
const majorOptions = ref<PartMajorCategory[]>([])
const majorLabelById = computed(() => {
  const m: Record<string, string> = {}
  for (const it of majorOptions.value) if (it.id != null) m[String(it.id)] = it.major_category
  return m
})
function majorLabel(v: string): string {
  return majorLabelById.value[v] || v
}
async function loadMajors() {
  try {
    const res = await partsApi.majorCategories()
    majorOptions.value = res.major_categories || []
  } catch {
    majorOptions.value = []
  }
}

const route = useRoute()
const router = useRouter()
// 从路由参数取机型（卡片入口 /servers/drawing/:modelId），无参数时进页后默认第一个
const modelId = ref<number | null>(route.params.modelId ? Number(route.params.modelId) : null)
const view = ref<DrawingViewType>('top')
const viewOptions = [
  { value: 'top', label: '俯视图' },
  { value: 'front', label: '前视图' },
  { value: 'rear', label: '后视图' },
]
const svgUrl = ref<string | null>(null)
const viewBox = ref<DrawingViewBox | null>(null)
const regions = ref<DrawingRegion[]>([])
const loading = ref(false)
const saving = ref(false)
const editorRef = ref<InstanceType<typeof ServerAnatomyEditor> | null>(null)
const activeUid = ref<string | null>(null)

// ── 图层状态 ──
const layersMeta = ref<DrawingLayerMeta[]>([])
const svgElRef = ref<SVGSVGElement | null>(null)
const activeLayerId = ref<string | null>(null)
const layerDirty = ref(false)
const tab = ref<'regions' | 'layers'>('regions')

// ── 版本历史 ──
const versions = ref<DrawingVersion[]>([])
const versionsOpen = ref(false)
const versionsLoading = ref(false)
const versionsBusy = ref(false)
const rollingVersionId = ref<string | null>(null)
const deletingVersionId = ref<string | null>(null)
const hasHistory = computed(() => versions.value.some(v => !v.is_current))
const hasMissingFile = computed(() => versions.value.some(v => v.file_exists === false))

function formatTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}

async function loadVersions() {
  if (!modelId.value) return
  versionsLoading.value = true
  try {
    const res = await serverDrawingApi.listVersions(modelId.value, view.value)
    versions.value = res.versions || []
  } catch {
    versions.value = []
  } finally {
    versionsLoading.value = false
  }
}

function openVersions() {
  loadVersions()
  versionsOpen.value = true
}

async function rollbackTo(versionId?: string) {
  if (!modelId.value) return
  versionsBusy.value = true
  rollingVersionId.value = versionId || null
  try {
    await serverDrawingApi.rollback(modelId.value, view.value, versionId)
    message.success('已回退到指定版本')
    versionsOpen.value = false
    await loadDrawing()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '回退失败')
  } finally {
    versionsBusy.value = false
    rollingVersionId.value = null
  }
}

async function removeVersion(versionId: string) {
  if (!modelId.value) return
  deletingVersionId.value = versionId
  try {
    const res = await serverDrawingApi.deleteVersion(modelId.value, versionId, view.value)
    message.success('版本已删除' + (res.removed_files ? `（清理 ${res.removed_files} 个文件）` : ''))
    await loadVersions()
    await loadDrawing()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '删除失败')
  } finally {
    deletingVersionId.value = null
  }
}

function confirmDeleteDrawing() {
  Modal.confirm({
    title: '删除当前图纸',
    content: '将删除该机型的整张图纸配置与全部历史版本，相关 SVG 文件也会一并清理。此操作不可恢复。',
    okType: 'danger',
    okText: '删除',
    cancelText: '取消',
    onOk: async () => {
      if (!modelId.value) return
      try {
        const res = await serverDrawingApi.deleteDrawing(modelId.value, view.value)
        message.success('图纸已删除' + (res.removed_files ? `（清理 ${res.removed_files} 个文件）` : ''))
        versionsOpen.value = false
        await loadDrawing()
        await loadVersions()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除失败')
      }
    },
  })
}

const svgRevision = ref(0)
const layerNodes = computed<SvgLayerNode[]>(() => {
  void svgRevision.value
  if (!svgElRef.value) return []
  const out = parseSvgLayers(svgElRef.value, layersMeta.value)
  return out
})

const activeLayerNode = computed<SvgLayerNode | null>(() => findNode(layerNodes.value, activeLayerId.value))
function findNode(nodes: SvgLayerNode[], id: string | null): SvgLayerNode | null {
  if (!id) return null
  for (const n of nodes) {
    if (n.id === id) return n
    const f = findNode(n.children, id)
    if (f) return f
  }
  return null
}
// 区域（热区）事件
function onRegionsChange(rs: DrawingRegion[]) { regions.value = rs }
function onSelect(uid: string | null) { activeUid.value = uid }
function selectRegion(uid: string) { editorRef.value?.selectRegion(uid) }
function editRegion(uid: string) { editorRef.value?.openForm(uid) }
function removeRegion(uid: string) { editorRef.value?.removeRegion(uid) }

// 图层事件
function onSvgReady(svg: SVGSVGElement) { svgElRef.value = svg }
function onLayerSelect(id: string | null) { activeLayerId.value = id }
function onLayerChanged() { layerDirty.value = true; svgRevision.value++ }
// 图层面板：排序 / 拖拽 / 复制 / 删除（桥接到画布编辑器，编辑后自动刷新面板）
function onReorder(id: string, dir: 'up' | 'down' | 'top' | 'bottom') { editorRef.value?.moveLayer(id, dir) }
function onMoveBefore(id: string, targetId: string) { editorRef.value?.moveLayerBefore(id, targetId) }
function onReparent(id: string, targetId: string) { editorRef.value?.reparentLayer(id, targetId) }
function onDuplicateLayer(id: string) { editorRef.value?.duplicateLayer(id) }
function onRemoveLayer(id: string) {
  editorRef.value?.removeLayer(id)
  if (activeLayerId.value === id) activeLayerId.value = null
}
function updateLayerMeta(id: string, patch: Partial<DrawingLayerMeta>) {
  const cur = layersMeta.value.find(m => m.id === id) || { id }
  const merged = { ...cur, ...patch }
  // 只有 id 的条目没意义，剔除
  const arr = layersMeta.value.filter(m => m.id !== id)
  if (Object.keys(merged).length > 1) arr.push(merged)
  layersMeta.value = arr
}
function onRename(id: string, name: string) { updateLayerMeta(id, { name }) }
function onToggleVisible(id: string, visible: boolean) { updateLayerMeta(id, { visible }) }
function onToggleLocked(id: string, locked: boolean) { updateLayerMeta(id, { locked }) }
function onSetOpacity(id: string, opacity: number) { updateLayerMeta(id, { opacity }) }
function onApplyTemplate(ids: string[], prefix: string) {
  ids.forEach((id, i) => updateLayerMeta(id, { name: templateName(prefix, i) }))
  message.success('命名模板已应用')
}

// 图层属性面板
function onPropName(name: string) { if (activeLayerId.value) onRename(activeLayerId.value, name) }
function onPropFill(v: string) { editorRef.value?.setLayerProp('fill', v) }
function onPropStroke(v: string) { editorRef.value?.setLayerProp('stroke', v) }
function onPropOpacity(v: number) {
  editorRef.value?.setLayerProp('opacity', String(v))
  if (activeLayerId.value) updateLayerMeta(activeLayerId.value, { opacity: v })
}
function onPropRect(part: { x?: number; y?: number; w?: number; h?: number }) { editorRef.value?.setLayerRect(part) }
function removeActiveLayer() { if (activeLayerId.value) { editorRef.value?.removeLayer(activeLayerId.value); activeLayerId.value = null } }
function duplicateActiveLayer() { if (activeLayerId.value) editorRef.value?.duplicateLayer(activeLayerId.value) }
function resetActiveTransform() { editorRef.value?.resetLayerTransform() }

// 保存图纸编辑（编辑器工具栏「保存图纸」）
async function onSaveSvg(svg: string) {
  if (!modelId.value) return
  saving.value = true
  try {
    const res = await serverDrawingApi.saveSvg(modelId.value, view.value, svg)
    await serverDrawingApi.save(modelId.value, {
      view: view.value, viewBox: res.viewBox, regions: regions.value, layers: layersMeta.value,
    })
    message.success('图纸编辑已保存')
    await loadDrawing()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
function saveDrawingEdit() { editorRef.value?.saveLayers() }

// ── 替换向导 ──
interface ReplaceReport {
  newUrl: string
  newViewBox: DrawingViewBox | null
  matched: string[]
  lost: string[]
  newIds: string[]
  migratedRegions: DrawingRegion[]
}
const replaceOpen = ref(false)
const replaceBusy = ref(false)
const replaceReport = ref<ReplaceReport | null>(null)

function scaleRegion(r: DrawingRegion, oldVb: DrawingViewBox | null, newVb: DrawingViewBox | null): DrawingRegion {
  if (!oldVb || !newVb) return r
  const [ox, oy, ow, oh] = oldVb
  const [nx, ny, nw, nh] = newVb
  const sx = nw / ow
  const sy = nh / oh
  return {
    ...r,
    x: Math.round((r.x - ox) * sx + nx),
    y: Math.round((r.y - oy) * sy + ny),
    width: Math.round(r.width * sx),
    height: Math.round(r.height * sy),
  }
}

async function onReplaceUpload(file: File) {
  if (!modelId.value) return false
  if (!/.svg$/i.test(file.name)) { message.error('仅支持 .svg 图纸'); return false }
  replaceBusy.value = true
  try {
    const res = await serverDrawingApi.uploadSvg(modelId.value, view.value, file)
    const txt = await (await fetch(res.url)).text()
    const doc = new DOMParser().parseFromString(txt, 'image/svg+xml')
    const newIds = [...new Set<string>(
      [...doc.querySelectorAll('[id]')].map(e => e.getAttribute('id') || '').filter(Boolean)
    )]
    const oldIds = layersMeta.value.map(m => m.id)
    const matched = oldIds.filter(id => newIds.includes(id))
    const lost = oldIds.filter(id => !newIds.includes(id))
    replaceReport.value = {
      newUrl: res.url,
      newViewBox: res.viewBox,
      matched,
      lost,
      newIds,
      migratedRegions: regions.value.map(r => scaleRegion(r, viewBox.value, res.viewBox)),
    }
    message.success('新图纸已上传（旧图已自动备份），请确认绑定结果')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
    replaceReport.value = null
  } finally {
    replaceBusy.value = false
  }
  return false
}

async function applyReplace() {
  if (!modelId.value || !replaceReport.value) return
  replaceBusy.value = true
  try {
    const rp = replaceReport.value
    const keptLayers = layersMeta.value.filter(m => rp.matched.includes(m.id))
    await serverDrawingApi.save(modelId.value, {
      view: view.value, viewBox: rp.newViewBox, regions: rp.migratedRegions, layers: keptLayers,
    })
    message.success('替换已应用（旧图已备份，可随时回退）')
    replaceOpen.value = false
    replaceReport.value = null
    await loadDrawing()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '应用失败')
  } finally {
    replaceBusy.value = false
  }
}

async function cancelReplace() {
  if (!modelId.value) return
  replaceBusy.value = true
  try {
    await serverDrawingApi.rollback(modelId.value, view.value)
    message.success('已取消替换，恢复原图纸')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '回退失败')
  } finally {
    replaceBusy.value = false
    replaceOpen.value = false
    replaceReport.value = null
    await loadDrawing()
  }
}

// ── 加载 ──
async function loadModels() {
  try {
    const res = await catalogApi.listModels()
    models.value = res.models || []
    if (!modelId.value && models.value.length) modelId.value = models.value[0].id
  } catch {
    message.error('机型列表加载失败')
  }
}

async function loadDrawing() {
  if (!modelId.value) return
  loading.value = true
  try {
    const v = await serverDrawingApi.get(modelId.value, view.value)
    svgUrl.value = v?.svg_url || null
    viewBox.value = v?.viewBox || null
    regions.value = v?.regions || []
    layersMeta.value = v?.layers || []
    svgElRef.value = null
    activeLayerId.value = null
    layerDirty.value = false
    tab.value = 'regions'
  } catch {
    message.error('图纸配置读取失败')
  } finally {
    loading.value = false
    loadVersions()
  }
}

async function onUpload(file: File) {
  if (!modelId.value) {
    message.warning('请先选择机型')
    return false
  }
  if (!/\.svg$/i.test(file.name)) {
    message.error('仅支持 .svg 图纸')
    return false
  }
  try {
    const res = await serverDrawingApi.uploadSvg(modelId.value, view.value, file)
    svgUrl.value = res.url
    viewBox.value = res.viewBox
    regions.value = res.regions || []
    message.success('图纸已上传（已自动备份旧版，可在「替换图纸」中回退）')
    await loadDrawing()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  }
  return false // 阻止 a-upload 默认行为
}

async function save() {
  if (!modelId.value) return
  if (!regions.value.length) {
    message.warning('还没有标注区域，先在图上圈出区域')
    return
  }
  saving.value = true
  try {
    await serverDrawingApi.save(modelId.value, { view: view.value, viewBox: viewBox.value, regions: regions.value, layers: layersMeta.value })
    message.success('标注已保存')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const currentModelName = computed(() => models.value.find(m => m.id === modelId.value)?.name || '')

watch(modelId, loadDrawing, { immediate: true })
watch(view, loadDrawing)
onMounted(() => { loadModels(); loadMajors() })
</script>

<template>
  <div class="sdc">
    <header class="sdc-head">
      <a class="sdc-back" @click="router.push('/servers/admin?tab=drawing')">← 返回图纸列表</a>
      <div class="sdc-title">服务器图纸配置</div>
      <p class="sdc-sub">上传机型 SVG 图纸 → 标注区域 / 编辑图层（显隐·重命名·移动·缩放）→ 选型配置页点击区域查看相关规则</p>
    </header>

    <div class="sdc-body">      <aside class="sdc-panel sdc-left">
        <div class="sdc-panel-title">图纸配置</div>
        <div class="sdc-field">
          <span class="sdc-label">机型</span>
          <a-select v-model:value="modelId" :options="models.map(m => ({ value: m.id, label: m.name }))"
            placeholder="选择机型" style="width: 100%" show-search option-filter-prop="label" />
        </div>
        <div class="sdc-field">
          <span class="sdc-label">视图</span>
          <a-select v-model:value="view" :options="viewOptions" style="width: 100%" />
        </div>
        <div class="sdc-field">
          <span class="sdc-label">图纸</span>
          <a-upload :show-upload-list="false" :before-upload="onUpload" accept=".svg" style="flex: 1">
            <a-button block size="small"><UploadOutlined /> 上传 SVG 图纸</a-button>
          </a-upload>
        </div>
        <div class="sdc-status">
          <a-tag v-if="svgUrl" color="green">已上传图纸</a-tag>
          <a-tag v-else color="default">未上传</a-tag>
          <a-tag v-if="hasHistory" color="orange">有历史版本</a-tag>
          <a-tag v-if="hasMissingFile" color="red">存在文件缺失版本</a-tag>
        </div>
        <a-button type="primary" block :loading="saving" @click="save"><SaveOutlined /> 保存标注</a-button>
        <a-button block :disabled="!layerDirty" @click="saveDrawingEdit">保存图纸编辑</a-button>
        <a-space style="width: 100%" :size="8">
          <a-button block size="small" @click="replaceOpen = true"><SwapOutlined /> 替换图纸</a-button>
          <a-button block size="small" @click="openVersions"><HistoryOutlined /> 版本历史</a-button>
        </a-space>
        <p class="sdc-note">当前机型：{{ currentModelName }}<template v-if="viewBox"> · viewBox {{ viewBox.join(', ') }}</template></p>
        <p class="sdc-note">替换/编辑图纸会自动备份旧版；版本历史支持回退与删除，删除版本会同步清理后端 SVG 文件。</p>
      </aside>

      <main class="sdc-center">
        <a-spin :spinning="loading">
          <ServerAnatomyEditor
            v-if="modelId"
            ref="editorRef"
            :key="String(modelId) + view"
            :svg-url="svgUrl"
            :view-box="viewBox"
            :regions="regions"
            :layers="layersMeta"
            @change="onRegionsChange"
            @select="onSelect"
            @layer-select="onLayerSelect"
            @layer-changed="onLayerChanged"
            @svg-ready="onSvgReady"
            @save-svg="onSaveSvg"
          />
          <a-empty v-else description="暂无机型，请先到服务器管理创建机型" />
        </a-spin>
      </main>

      <aside class="sdc-panel sdc-right">
        <a-tabs v-model:activeKey="tab" size="small" class="sdc-tabs">
          <a-tab-pane key="regions" tab="区域列表">
            <div v-if="regions.length" class="sdc-regions">
              <div v-for="r in regions" :key="r.uid" class="sdc-region-item" :class="{ on: activeUid === r.uid }"
                @click="selectRegion(r.uid)">
                <div class="sdc-region-top">
                  <span class="sdc-region-name">{{ r.name || '（未命名）' }}</span>
                  <span class="sdc-region-type">{{ majorLabel(r.region_type) }}</span>
                </div>
                <div class="sdc-region-xy">{{ r.x }},{{ r.y }} · {{ r.width }}×{{ r.height }}</div>
                <div class="sdc-region-ops">
                  <a size="small" @click.stop="editRegion(r.uid)">编辑</a>
                  <a size="small" class="sdc-danger" @click.stop="removeRegion(r.uid)">删除</a>
                </div>
              </div>
            </div>
            <a-empty v-else description="还没有区域，在画布上拖拽圈出区域" />
            <div class="sdc-tips">
              <div class="sdc-tips-title">操作提示</div>
              <ul>
                <li>绘制模式：拖拽拉出矩形区域</li>
                <li>选择模式：点区域移动，拖四角拉伸</li>
                <li>图层模式：点选元素移动 / 控制点缩放 / 顶部手柄旋转</li>
                <li>滚轮：缩放画布 · 按住中键拖动：平移画布</li>
              </ul>
            </div>
          </a-tab-pane>

          <a-tab-pane key="layers" tab="图层面板">
                        <SvgLayerPanel
              :key="String(modelId) + view"
              :nodes="layerNodes"
              :active-id="activeLayerId"
              @select="(id: string | null) => editorRef?.selectLayer(id)"
              @rename="onRename"
              @toggle-visible="onToggleVisible"
              @toggle-locked="onToggleLocked"
              @set-opacity="onSetOpacity"
              @apply-template="onApplyTemplate"
              @reorder="onReorder"
              @move-before="onMoveBefore"
              @reparent="onReparent"
              @duplicate="onDuplicateLayer"
              @remove="onRemoveLayer"
            />
            <div v-if="activeLayerNode" class="sdc-layerprop">
              <div class="sdc-tips-title">图层属性 · {{ activeLayerNode.tag }}</div>
              <div class="sdc-field">
                <span class="sdc-label">名称</span>
                <a-input size="small" :value="activeLayerNode.name" @change="(e: any) => onPropName(e.target.value)" />
              </div>
              <div class="sdc-prop-grid">
                <div class="sdc-field"><span class="sdc-label">X</span>
                  <a-input-number size="small" style="width: 100%" :value="Math.round(activeLayerNode.bbox?.x || 0)" :disabled="activeLayerNode.tag !== 'rect'" @change="(v: number | null) => onPropRect({ x: v ?? 0 })" /></div>
                <div class="sdc-field"><span class="sdc-label">Y</span>
                  <a-input-number size="small" style="width: 100%" :value="Math.round(activeLayerNode.bbox?.y || 0)" :disabled="activeLayerNode.tag !== 'rect'" @change="(v: number | null) => onPropRect({ y: v ?? 0 })" /></div>
                <div class="sdc-field"><span class="sdc-label">宽</span>
                  <a-input-number size="small" style="width: 100%" :value="Math.round(activeLayerNode.bbox?.w || 0)" :disabled="activeLayerNode.tag !== 'rect'" @change="(v: number | null) => onPropRect({ w: v ?? 0 })" /></div>
                <div class="sdc-field"><span class="sdc-label">高</span>
                  <a-input-number size="small" style="width: 100%" :value="Math.round(activeLayerNode.bbox?.h || 0)" :disabled="activeLayerNode.tag !== 'rect'" @change="(v: number | null) => onPropRect({ h: v ?? 0 })" /></div>
              </div>
              <template v-if="activeLayerNode.tag !== 'g'">
                <div class="sdc-field">
                  <span class="sdc-label">填充</span>
                  <a-input size="small" type="color" style="padding: 0 4px; height: 28px" @change="(e: any) => onPropFill(e.target.value)" />
                </div>
                <div class="sdc-field">
                  <span class="sdc-label">描边</span>
                  <a-input size="small" type="color" style="padding: 0 4px; height: 28px" @change="(e: any) => onPropStroke(e.target.value)" />
                </div>
              </template>
              <div class="sdc-field">
                <span class="sdc-label">透明度 {{ Math.round(activeLayerNode.opacity * 100) }}%</span>
                <a-slider :min="0" :max="100" size="small" :value="Math.round(activeLayerNode.opacity * 100)"
                  @change="(v: number) => onPropOpacity((v || 0) / 100)" />
              </div>
              <a-space wrap style="margin-top: 6px">
                <a-button size="small" danger @click="removeActiveLayer">删除图层</a-button>
                <a-button size="small" @click="duplicateActiveLayer">复制图层</a-button>
                <a-button size="small" @click="resetActiveTransform">重置变换</a-button>
              </a-space>
              <p class="sdc-note">几何仅 rect 元素可直接编辑；组/path 请用画布拖动/控制点。改完点「保存图纸编辑」落盘。</p>
            </div>
            <a-empty v-else description="在图上点选元素，或在左侧勾选图层查看属性" />
          </a-tab-pane>
        </a-tabs>
      </aside>
    </div>

    <!-- 替换向导 -->
    <a-modal v-model:open="replaceOpen" title="替换图纸" :footer="null" width="560px" :mask-closable="false">
      <p class="sdc-note" style="margin-bottom: 8px">
        上传新 SVG 后系统会：① 自动备份当前图纸（可回退）；② 比对图层绑定；③ 按 viewBox 比例迁移区域坐标。
      </p>
      <a-upload :show-upload-list="false" :before-upload="onReplaceUpload" accept=".svg">
        <a-button block :loading="replaceBusy"><UploadOutlined /> 选择新 SVG 图纸</a-button>
      </a-upload>
      <div v-if="replaceReport" style="margin-top: 12px; display: flex; flex-direction: column; gap: 10px">
        <a-alert type="info" show-icon :message="'新图已上传（' + replaceReport.newIds.length + ' 个图层元素）'" />
        <div class="sdc-rep-block">
          <div class="sdc-tips-title">✅ 自动跟随（{{ replaceReport.matched.length }}）</div>
          <div v-if="replaceReport.matched.length" class="sdc-rep-tags">
            <a-tag v-for="id in replaceReport.matched" :key="id" color="green">{{ id }}</a-tag>
          </div>
          <div v-else class="sdc-note">无已编辑图层，跳过</div>
        </div>
        <div class="sdc-rep-block">
          <div class="sdc-tips-title">❌ 新图中未找到（{{ replaceReport.lost.length }}）</div>
          <div v-if="replaceReport.lost.length" class="sdc-rep-tags">
            <a-tag v-for="id in replaceReport.lost" :key="id" color="red">{{ id }}</a-tag>
          </div>
          <div v-else class="sdc-note">无丢失绑定</div>
        </div>
        <div class="sdc-rep-block">
          <div class="sdc-tips-title">区域坐标迁移</div>
          <div class="sdc-note">
            原 viewBox {{ viewBox ? viewBox.join(',') : '-' }} → 新 {{ replaceReport.newViewBox ? replaceReport.newViewBox.join(',') : '-' }}
            ，{{ regions.length }} 个区域按比例换算，确认后写入。
          </div>
        </div>
        <a-space>
          <a-button type="primary" :loading="replaceBusy" @click="applyReplace">确认应用</a-button>
          <a-button :loading="replaceBusy" @click="cancelReplace">取消并回退</a-button>
        </a-space>
      </div>
    </a-modal>

    <!-- 版本历史 -->
    <a-modal v-model:open="versionsOpen" title="版本历史" :footer="null" width="660px" :mask-closable="false">
      <a-spin :spinning="versionsLoading">
        <div v-if="!versions.length" style="padding: 20px 0; text-align: center; color: var(--cpq-text-muted)">暂无版本</div>
        <div v-else style="display: flex; flex-direction: column; gap: 8px; max-height: 420px; overflow-y: auto">
          <div v-for="ver in versions" :key="ver.id" class="sdc-ver-row">
            <div class="sdc-ver-info">
              <span class="sdc-ver-name" :title="ver.svg_url">{{ ver.svg_url ? ver.svg_url.split('/').pop() : '未上传' }}</span>
              <a-tag v-if="ver.is_current" color="blue">当前</a-tag>
              <a-tag v-else color="default">历史</a-tag>
              <a-tag :color="ver.file_exists ? 'green' : 'red'">{{ ver.file_exists ? '文件存在' : '文件缺失' }}</a-tag>
            </div>
            <div class="sdc-ver-meta">
              <span>{{ ver.created_at ? formatTime(ver.created_at) : '导入时间未知' }}</span>
              <span>{{ ver.regions.length }} 个区域</span>
            </div>
            <div class="sdc-ver-actions">
              <a-button v-if="!ver.is_current" size="small" :disabled="!ver.file_exists"
                :loading="versionsBusy && rollingVersionId === ver.id" @click="rollbackTo(ver.id)">
                <RollbackOutlined /> 回退
              </a-button>
              <a-button v-if="!ver.is_current" size="small" danger :loading="deletingVersionId === ver.id"
                @click="removeVersion(ver.id)">
                <DeleteOutlined /> 删除
              </a-button>
            </div>
          </div>
        </div>
        <a-divider style="margin: 12px 0" />
        <a-button block danger @click="confirmDeleteDrawing"><DeleteOutlined /> 删除当前图纸（含全部历史版本）</a-button>
        <p class="sdc-note" style="margin-top: 8px">删除版本会同步清理后端 SVG 文件；若文件仍被其他版本引用则自动保留。文件缺失的版本不可回退，可直接删除。</p>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.sdc { display: flex; flex-direction: column; gap: 12px; height: 100%; min-height: 540px; min-width: 1080px; padding: 4px 0 24px; }
.sdc-head { display: flex; flex-direction: column; gap: 4px; flex-shrink: 0; }
.sdc-back { font-size: 13px; color: var(--cpq-accent-primary); cursor: pointer; width: fit-content; }
.sdc-back:hover { text-decoration: underline; }
.sdc-title { font-size: 22px; font-weight: 700; color: var(--cpq-text-primary); }
.sdc-sub { margin: 0; color: var(--cpq-text-secondary); font-size: 13px; }
.sdc-body { display: flex; gap: 12px; flex: 1; min-height: 0; }
.sdc-panel { display: flex; flex-direction: column; gap: 12px; padding: 14px; border-radius: 12px;
  background: var(--cpq-overlay-a6, rgba(255, 255, 255, 0.03)); border: 1px solid var(--cpq-glass-border); }
.sdc-left { width: 250px; flex-shrink: 0; overflow-y: auto; }
.sdc-right { width: 320px; flex-shrink: 0; overflow-y: auto; }
.sdc-panel-title { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--cpq-text-primary); flex-shrink: 0; }
.sdc-count { padding: 0 8px; border-radius: 10px; font-size: 12px; line-height: 18px;
  background: var(--cpq-accent-primary); color: #fff; }
.sdc-field { display: flex; flex-direction: column; gap: 4px; }
.sdc-label { color: var(--cpq-text-secondary); font-size: 12px; }
.sdc-status { display: flex; flex-wrap: wrap; gap: 6px; }
.sdc-note { margin: 0; color: var(--cpq-text-muted); font-size: 12px; line-height: 1.6; }
.sdc-center { position: relative; flex: 1; min-width: 0; overflow: hidden; }
.sdc-center :deep(.ant-spin-nested-loading), .sdc-center :deep(.ant-spin-container) { position: absolute; inset: 0; display: flex; }
.sdc-center :deep(.sae) { flex: 1; min-width: 0; }
.sdc-center :deep(.ant-empty) { margin: auto; }
.sdc-tabs { height: 100%; }
.sdc-tabs :deep(.ant-tabs-content-holder) { overflow: auto; }
.sdc-tabs :deep(.ant-tabs-content), .sdc-tabs :deep(.ant-tabs-tabpane) { height: 100%; }
.sdc-regions { display: flex; flex-direction: column; gap: 8px; overflow-y: auto; flex: 1; }
.sdc-region-item { border: 1px solid var(--cpq-glass-border); border-radius: 10px; padding: 8px 10px; cursor: pointer; }
.sdc-region-item.on { border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); }
.sdc-region-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.sdc-region-name { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sdc-region-type { color: var(--cpq-accent-primary); font-size: 12px; flex-shrink: 0; }
.sdc-region-xy { color: var(--cpq-text-muted); font-size: 12px; margin-top: 2px; }
.sdc-region-ops { display: flex; gap: 14px; margin-top: 4px; font-size: 12px; }
.sdc-danger { color: #ff4d4f; }
.sdc-tips { border-top: 1px dashed var(--cpq-glass-border); padding-top: 10px; flex-shrink: 0; }
.sdc-tips-title { font-weight: 600; color: var(--cpq-text-secondary); font-size: 12px; margin-bottom: 6px; }
.sdc-tips ul { margin: 0; padding-left: 16px; color: var(--cpq-text-muted); font-size: 12px;
  display: flex; flex-direction: column; gap: 4px; }
.sdc-layerprop { border-top: 1px dashed var(--cpq-glass-border); padding-top: 10px; margin-top: 10px;
  display: flex; flex-direction: column; gap: 8px; }
.sdc-prop-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.sdc-rep-block { display: flex; flex-direction: column; gap: 6px; }
.sdc-rep-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.sdc-ver-row { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; border: 1px solid var(--cpq-glass-border); border-radius: 10px; }
.sdc-ver-info { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sdc-ver-name { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sdc-ver-meta { display: flex; gap: 12px; color: var(--cpq-text-muted); font-size: 12px; }
.sdc-ver-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
