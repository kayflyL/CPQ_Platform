<script setup lang="ts">
/** 机型产品化包装编辑页（管理面，单栏流式）。
 *  基本信息 + 关联基准配置（一对多·配置变体）+ 主图 + 产品内容（与详情页展示顺序一致：
 *  一句话定位/概述/价值亮点/能力板块/场景适配/完整技术规格）。
 *  路由复用：/servers/models/new 与 /servers/models/:modelId/edit 同一组件。
 *  新建机型保存后留在本页（关联配置需要先有机型 id）。 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import axios from 'axios'
import {
  catalogApi, baseConfigApi,
  type ServerType, type ServerModel, type BaseConfig, type ModelProductContent, type ConfigContent,
  type ModelScenario,
} from '@/api/serverConfig'
import { CAP_ICON_KEYS, capIconSvg } from '@/constants/capIcons'

type LifecycleStatus = 'new' | 'active' | 'eol' | 'discontinued'
const LIFECYCLES: { value: LifecycleStatus; label: string }[] = [
  { value: 'new', label: '新品' },
  { value: 'active', label: '在售' },
  { value: 'eol', label: '即将停产' },
  { value: 'discontinued', label: '停产' },
]

const route = useRoute()
const router = useRouter()
const editingId = ref<number | null>(null)
const loading = ref(false)
const saving = ref(false)

const types = ref<ServerType[]>([])
const scenarioOptions = ref<{ label: string; value: string }[]>([])

const form = ref<{
  name?: string
  server_type_id?: number
  base_config_id?: number
  lifecycle_status?: LifecycleStatus
  is_published?: boolean
  image_url?: string
  product_content: ModelProductContent
}>({
  lifecycle_status: 'active',
  is_published: true,
  product_content: { tagline: '', overview: '', stage_theme: 'ocean', highlight_image: '', highlights: [], capabilities: [], specs: [], scenarios: [] },
})

const typeName = (id?: number) => types.value.find(t => t.id === id)?.name || '—'

// ---- 关联基准配置（一对多·配置变体）----
const modelConfigs = ref<BaseConfig[]>([])          // 本机型已关联的配置（含主配置）
const unassignedConfigs = ref<BaseConfig[]>([])     // 孤儿配置池（可供关联）
const linkModalOpen = ref(false)
const linkSearch = ref('')
const linking = ref(false)
const contentEditId = ref<number | null>(null)      // 正在内联编辑 config_content 的 config id
const contentDraft = ref<ConfigContent>({ description: '', spec_diff: '' })
const contentSaving = ref(false)

const filteredUnassigned = computed(() => {
  const kw = linkSearch.value.trim().toLowerCase()
  const list = unassignedConfigs.value
  if (!kw) return list
  return list.filter(c =>
    (c.name || '').toLowerCase().includes(kw) || (c.series || '').toLowerCase().includes(kw)
  )
})

async function refreshConfigs() {
  if (!editingId.value) return
  const m = await catalogApi.getModel(editingId.value)
  modelConfigs.value = m.configs || []
  form.value.base_config_id = m.base_config_id   // 同步主配置
  const res = await baseConfigApi.list({ unassigned: true })
  unassignedConfigs.value = res.configs
}

function openLinkModal() {
  linkSearch.value = ''
  linkModalOpen.value = true
}

async function confirmLink(cfg: BaseConfig) {
  if (!editingId.value) return
  linking.value = true
  try {
    await baseConfigApi.update(cfg.id!, { model_id: editingId.value })
    message.success(`已关联「${cfg.name}」`)
    linkModalOpen.value = false
    await refreshConfigs()
    // 首个关联的配置自动设为主配置
    if (form.value.base_config_id == null && modelConfigs.value.length === 1) {
      await setDefault(modelConfigs.value[0])
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally { linking.value = false }
}

async function unlinkConfig(cfg: BaseConfig) {
  try {
    await baseConfigApi.update(cfg.id!, { model_id: null })
    message.success('已取消关联')
    // 若取消的是主配置，自动把主配置挪到剩余的第一个
    if (form.value.base_config_id === cfg.id) {
      const remaining = modelConfigs.value.filter(c => c.id !== cfg.id)
      form.value.base_config_id = remaining[0]?.id
      if (editingId.value) {
        await catalogApi.updateModel(editingId.value, { base_config_id: form.value.base_config_id })
      }
    }
    await refreshConfigs()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}

async function setDefault(cfg: BaseConfig) {
  if (!editingId.value || form.value.base_config_id === cfg.id) return
  form.value.base_config_id = cfg.id
  try {
    await catalogApi.updateModel(editingId.value, { base_config_id: cfg.id })
    message.success(`已设「${cfg.name}」为主配置`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '设置失败')
  }
}

function goEditConfig(cfg: BaseConfig) {
  router.push({ path: `/servers/base-configs/${cfg.id}` })
}

function toggleContentEdit(cfg: BaseConfig) {
  if (contentEditId.value === cfg.id) { contentEditId.value = null; return }
  contentEditId.value = cfg.id
  contentDraft.value = {
    description: cfg.config_content?.description || '',
    spec_diff: cfg.config_content?.spec_diff || '',
  }
}

async function saveConfigContent(cfg: BaseConfig) {
  contentSaving.value = true
  try {
    // 合并保存：只覆盖 description/spec_diff，保留 standard_riser/riser_x16/standard_mem_speed（否则会被清掉）
    const cc: Record<string, any> = { ...(cfg.config_content || {}) }
    if (contentDraft.value.description?.trim()) cc.description = contentDraft.value.description.trim()
    else delete cc.description
    if (contentDraft.value.spec_diff?.trim()) cc.spec_diff = contentDraft.value.spec_diff.trim()
    else delete cc.spec_diff
    await baseConfigApi.update(cfg.id!, { config_content: cc })
    message.success('配置简介已保存')
    contentEditId.value = null
    await refreshConfigs()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { contentSaving.value = false }
}

// ---- 产品内容增删：亮点 / 能力维度（含关键数字）/ 场景 / 规格 ----
function addHighlight() {
  const list = form.value.product_content.highlights || (form.value.product_content.highlights = [])
  list.push({ title: '', text: '' })
}
function delHighlight(i: number) { form.value.product_content.highlights?.splice(i, 1) }
function addCap() {
  const caps = form.value.product_content.capabilities || (form.value.product_content.capabilities = [])
  caps.push({ name: '', name_en: '', icon: '', desc: '', metrics: [] })
}
function delCap(i: number) { form.value.product_content.capabilities?.splice(i, 1) }
function addMetric(ci: number) {
  const m = form.value.product_content.capabilities?.[ci]
  const list = m?.metrics || (m!.metrics = [])
  list.push({ v: '', l: '' })
}
function delMetric(ci: number, mi: number) { form.value.product_content.capabilities?.[ci]?.metrics?.splice(mi, 1) }
function addScn() {
  const list = form.value.product_content.scenarios || (form.value.product_content.scenarios = [])
  list.push({ name: '', fit: '', image: '' })
}
function delScn(i: number) { form.value.product_content.scenarios?.splice(i, 1) }
function addSpec() { form.value.product_content.specs?.push({ key: '', value: '' }) }
function delSpec(i: number) { form.value.product_content.specs?.splice(i, 1) }

/** 场景编辑行：归一化成对象（init 已迁移，此处兜底旧字符串），v-model 直改引用即写回 form */
const scnRows = computed<ModelScenario[]>(() =>
  (form.value.product_content.scenarios || []).map(s => (typeof s === 'string' ? { name: s, fit: '', image: '' } : s))
)

/** 场景名联想选项：跨机型收集历史场景（新结构存对象，旧结构存字符串，都取 name） */
const scnNameOptions = computed(() => scenarioOptions.value)

// ---- 图片上传（复用既有端点 POST /api/server-catalog/models/image，按用途+机型分类落盘）----
async function handleImageUpload(file: File): Promise<boolean> {
  try {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await axios.post('/api/server-catalog/models/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { type: 'product', ...(editingId.value ? { model_id: editingId.value } : {}) },
    })
    form.value.image_url = resp.data.url
    message.success('图片已上传')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  }
  return false
}

/** 场景配图上传：写回对应场景行的 image（未保存机型无 id，落旧平铺目录） */
async function uploadScnImage(i: number, file: File): Promise<boolean> {
  try {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await axios.post('/api/server-catalog/models/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { type: 'scenario', ...(editingId.value ? { model_id: editingId.value } : {}) },
    })
    const s: any = form.value.product_content.scenarios?.[i]
    if (s) s.image = resp.data.url
    message.success('场景配图已上传')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  }
  return false
}

/** 「为什么选它」模块配图上传：写入 highlight_image（同池落盘，自动汇聚门户图库） */
async function uploadHighlightImage(file: File): Promise<boolean> {
  try {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await axios.post('/api/server-catalog/models/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { type: 'highlight', ...(editingId.value ? { model_id: editingId.value } : {}) },
    })
    form.value.product_content.highlight_image = resp.data.url
    message.success('模块配图已上传')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  }
  return false
}

/** 复制场景配图链接（站内相对路径补全为绝对 URL，站外也能直接用） */
async function copyScnUrl(s: ModelScenario) {
  if (!s.image) return
  const full = /^https?:/.test(s.image) ? s.image : location.origin + s.image
  try {
    await navigator.clipboard.writeText(full)
    message.success('图片链接已复制')
  } catch {
    const ta = document.createElement('textarea')
    ta.value = full
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    message.success('图片链接已复制')
  }
}

async function init() {
  loading.value = true
  try {
    const [typesRes, modelsRes] = await Promise.all([
      catalogApi.listTypes(), catalogApi.listModels(),
    ])
    types.value = typesRes.types
    // 跨机型收集场景名历史（联想源；新结构存对象，旧结构存字符串，都取 name）
    const set = new Set<string>()
    for (const m of modelsRes.models) {
      const sc = m.product_content?.scenarios
      if (Array.isArray(sc)) sc.forEach(s => {
        const name = typeof s === 'string' ? s : s?.name
        if (name) set.add(name)
      })
    }
    scenarioOptions.value = [...set].sort().map(v => ({ label: v, value: v }))

    const id = route.params.modelId as string | undefined
    if (id && id !== 'new') {
      editingId.value = Number(id)
      const m: ServerModel = await catalogApi.getModel(editingId.value)
      const pc = m.product_content
      form.value = {
        name: m.name,
        server_type_id: m.server_type_id,
        base_config_id: m.base_config_id,
        lifecycle_status: (m.lifecycle_status as LifecycleStatus) || 'active',
        is_published: m.is_published !== false,
        image_url: m.image_url,
        product_content: {
          // 旧数据迁移：features[{icon,text}] → highlights[{title,text}]（保存后不再写 features）
          tagline: pc?.tagline || '',
          overview: pc?.overview || '',
          stage_theme: pc?.stage_theme || 'ocean',
          highlight_image: pc?.highlight_image || '',
          highlights: pc?.highlights?.length
            ? [...pc.highlights]
            : (pc?.features || []).map(f => ({ title: '', text: f.text })),
          capabilities: (pc?.capabilities || []).map(c => ({ ...c, metrics: c.metrics ? [...c.metrics] : [] })),
          specs: pc?.specs || [],
          // 旧结构 string[] → {name} 对象；保存后不再写字符串场景
          scenarios: (Array.isArray(pc?.scenarios) ? pc!.scenarios! : [])
            .map(s => (typeof s === 'string' ? { name: s, fit: '', image: '' } : { ...s })),
        },
      }
      modelConfigs.value = m.configs || []
      const res = await baseConfigApi.list({ unassigned: true })
      unassignedConfigs.value = res.configs
    } else {
      form.value.server_type_id = types.value[0]?.id
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally { loading.value = false }
}

async function save() {
  if (!form.value.name) return message.warning('请填机型名')
  saving.value = true
  try {
    const payload: Partial<ServerModel> = {
      name: form.value.name,
      server_type_id: form.value.server_type_id,
      base_config_id: form.value.base_config_id,
      lifecycle_status: form.value.lifecycle_status,
      is_published: form.value.is_published !== false,
      image_url: form.value.image_url,
      product_content: form.value.product_content,
    }
    if (editingId.value) {
      await catalogApi.updateModel(editingId.value, payload)
      message.success('已更新机型「' + form.value.name + '」')
    } else {
      const { id } = await catalogApi.createModel(payload)
      editingId.value = id
      message.success('已新建机型「' + form.value.name + '」，现在可关联配置变体')
      router.replace(`/servers/models/${id}/edit`)
      await refreshConfigs()
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}
function cancel() { router.push({ path: '/servers/admin', query: { refresh: 'models' } }) }

onMounted(init)
</script>

<template>
  <div class="editor-page">
    <div class="content-inner">
      <div class="cfg-bar glass">
        <div class="cfg-bar-left">
          <a-button class="btn-ghost" @click="cancel">← 返回</a-button>
          <h2 class="cfg-title">{{ editingId ? '编辑机型' : '新建机型' }}<span v-if="editingId" class="title-sub"> · {{ typeName(form.server_type_id) }}</span></h2>
        </div>
        <div class="cfg-bar-right">
          <a-button @click="cancel">取消</a-button>
          <a-button type="primary" :loading="saving" @click="save">保存</a-button>
        </div>
      </div>

      <a-spin :spinning="loading">
        <div class="single-col glass">
          <a-form layout="vertical">
            <!-- 基本信息 -->
            <div class="sec-label">基本信息</div>
            <a-row :gutter="12">
              <a-col :span="8"><a-form-item label="机型名" required><a-input v-model:value="form.name" placeholder="如 ES220 V3" /></a-form-item></a-col>
              <a-col :span="6"><a-form-item label="类型" required>
                <a-select v-model:value="form.server_type_id">
                  <a-select-option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
                </a-select>
              </a-form-item></a-col>
              <a-col :span="5"><a-form-item label="生命周期">
                <a-select v-model:value="form.lifecycle_status">
                  <a-select-option v-for="l in LIFECYCLES" :key="l.value" :value="l.value">{{ l.label }}</a-select-option>
                </a-select>
              </a-form-item></a-col>
              <a-col :span="5" v-if="!loading"><a-form-item label="是否上架">
                <div class="pub-cell">
                  <a-switch v-model:checked="form.is_published" />
                  <span class="pub-hint">{{ form.is_published ? '上架中 · 目录对外展示' : '已下架 · 目录隐藏；管理面/报价/推理流照旧' }}</span>
                </div>
              </a-form-item></a-col>
            </a-row>
            <a-row :gutter="12">
              <a-col :span="6">
                <a-form-item label="展示主题色">
                  <a-select v-model:value="form.product_content.stage_theme">
                    <a-select-option value="wine">酒红</a-select-option>
                    <a-select-option value="ocean">深蓝</a-select-option>
                    <a-select-option value="carbon">纯黑</a-select-option>
                    <a-select-option value="violet">暗紫</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 关联基准配置（一对多·配置变体） -->
            <div class="sec-label">关联基准配置（配置变体）<span class="sec-hint">一个机型可挂多个配置；单选其一为「主配置」（报价/选型默认用）</span></div>
            <div v-if="!editingId" class="empty-hint">保存机型后即可关联多个基准配置</div>
            <div v-else class="cfg-card-grid">
              <div v-for="cfg in modelConfigs" :key="cfg.id" class="ecfg-card">
                <div class="ecfg-card-head">
                  <a-radio :checked="form.base_config_id === cfg.id" @change="setDefault(cfg)">主配置</a-radio>
                  <span v-if="cfg.config_content?.description || cfg.config_content?.spec_diff" class="ecfg-badge">简介✓</span>
                </div>
                <div class="ecfg-name">{{ cfg.name }}</div>
                <div class="ecfg-spec">{{ cfg.series || '—' }} · {{ cfg.form || '—' }} · {{ cfg.bays ?? '—' }}盘</div>
                <div class="ecfg-actions">
                  <a-button size="small" link @click="toggleContentEdit(cfg)">{{ contentEditId === cfg.id ? '收起' : '编辑简介' }}</a-button>
                  <a-button size="small" link @click="goEditConfig(cfg)">编辑料件</a-button>
                  <a-popconfirm title="取消该配置与本机型的关联？" @confirm="unlinkConfig(cfg)">
                    <a-button size="small" link danger>取消关联</a-button>
                  </a-popconfirm>
                </div>
                <!-- 内联配置简介编辑（说明 + 规格差异，两段） -->
                <div v-if="contentEditId === cfg.id" class="ecfg-content-edit">
                  <a-textarea v-model:value="contentDraft.description" :rows="3" placeholder="该配置的说明（一段话，面向客户）" />
                  <a-textarea v-model:value="contentDraft.spec_diff" :rows="2" placeholder="规格差异说明（相对其他配置的不同点）" />
                  <div class="ecfg-content-foot">
                    <a-button size="small" type="primary" :loading="contentSaving" @click="saveConfigContent(cfg)">保存简介</a-button>
                  </div>
                </div>
              </div>
              <!-- ＋ 关联配置（打开选择面板） -->
              <div class="ecfg-card ecfg-card-add" @click="openLinkModal">
                <span class="ecfg-add-icon">＋</span>
                <span class="ecfg-add-text">关联配置</span>
              </div>
            </div>

            <!-- 选择基准配置面板：列出未归属配置，点选即关联 -->
            <a-modal v-model:open="linkModalOpen" title="选择基准配置关联到本机型" width="680px" :footer="null" destroyOnClose>
              <a-input-search v-model:value="linkSearch" placeholder="搜索配置名 / 系列" allowClear style="margin-bottom:12px" />
              <div class="link-cfg-list">
                <div v-for="c in filteredUnassigned" :key="c.id" class="link-cfg-item" @click="confirmLink(c)">
                  <div class="link-cfg-name">{{ c.name }}</div>
                  <div class="link-cfg-spec">{{ c.series || '—' }} · {{ c.form || '—' }} · {{ c.bays ?? '—' }}盘</div>
                </div>
                <div v-if="!filteredUnassigned.length" class="empty-hint">没有可关联的未归属配置（所有配置都已归属机型）</div>
              </div>
            </a-modal>

            <!-- 主图 -->
            <div class="sec-label">产品主图</div>
            <div class="img-row">
              <a-upload :before-upload="handleImageUpload" :show-upload-list="false" accept="image/*">
                <a-button>本地上传</a-button>
              </a-upload>
              <a-input v-model:value="form.image_url" class="kv-flex" placeholder="或粘贴图片 URL" allowClear />
            </div>
            <img v-if="form.image_url" :src="form.image_url" class="img-preview" alt="预览" />

            <!-- 产品内容：与详情页展示顺序一致（一句话定位 → 概述 → 价值亮点 → 能力 → 场景 → 规格） -->
            <div class="sec-label">一句话定位<span class="sec-hint">详情页铭牌副标题 · 15 字左右，如「AI 训推一体的国产算力底座」</span></div>
            <a-input v-model:value="form.product_content.tagline" placeholder="15 字左右，讲清这台机器是谁" allowClear />

            <div class="sec-label">产品概述<span class="sec-hint">详情页「产品概述」· 面向客户的一段话</span></div>
            <a-textarea v-model:value="form.product_content.overview" :rows="3" placeholder="面向客户的一段话产品介绍" />

            <div class="sec-label">价值亮点<span class="sec-hint">详情页「为什么选它」· 左图右文，每条 = 短标题 + 一句话</span></div>
            <div class="hl-editor-layout">
              <div class="hl-editor-photo">
                <a-upload :before-upload="uploadHighlightImage" :show-upload-list="false" accept="image/*">
                  <button type="button" class="hl-photo-drop" title="上传/更换模块配图">
                    <img v-if="form.product_content.highlight_image" :src="form.product_content.highlight_image" alt="" />
                    <span v-else class="hl-photo-drop-ph">模块配图</span>
                    <span class="up">⇪</span>
                  </button>
                </a-upload>
                <a-input v-model:value="form.product_content.highlight_image" size="small" allowClear placeholder="图片链接，可粘贴" />
              </div>
              <div class="hl-grid">
                <div v-for="(h, i) in form.product_content.highlights" :key="i" class="hl-card">
                  <a-input v-model:value="h.title" style="width:180px" placeholder="短标题（如：训推一体）" />
                  <a-input v-model:value="h.text" class="kv-flex" placeholder="一句话讲透价值（如：大模型微调与在线推理同机承载）" />
                  <a-button danger size="small" @click="delHighlight(i)">✕</a-button>
                </div>
                <!-- ＋ 添加亮点（虚线尾卡） -->
                <div class="hl-card hl-card-add" @click="addHighlight">
                  <span class="ecfg-add-icon">＋</span>
                  <span class="ecfg-add-text">添加亮点</span>
                </div>
              </div>
            </div>

            <div class="sec-label">
              能力板块
              <span class="sec-hint">详情页「产品能力」暗色带 · 写收益不写参数表，参数放技术规格</span>
            </div>
            <div class="cap-grid">
              <div v-for="(c, ci) in form.product_content.capabilities" :key="ci" class="cap-ed">
                <div class="cap-ed-head">
                  <a-input v-model:value="c.name" style="width:140px" placeholder="维度名（如：算力）" />
                  <a-input v-model:value="c.name_en" style="width:150px" placeholder="英文标签（如：Compute）" />
                  <a-button danger size="small" @click="delCap(ci)">✕</a-button>
                </div>
                <div class="ico-pick">
                  <button v-for="k in CAP_ICON_KEYS" :key="k" type="button" class="ico-btn"
                    :class="{ on: c.icon === k }" :title="k" @click="c.icon = k"
                    v-html="capIconSvg(k)"></button>
                </div>
                <a-textarea v-model:value="c.desc" :rows="2" placeholder="一句话价值 · 25 字左右。例：卡间互联无收敛，大模型训练不卡通信" />
                <div class="cap-ed-metrics">
                  <div class="cap-ed-metrics-label">关键数字</div>
                  <div v-for="(m, mi) in c.metrics" :key="mi" class="kv-row">
                    <a-input v-model:value="m.v" style="width:140px" placeholder="数字（如：8 卡）" />
                    <a-input v-model:value="m.l" style="width:200px" placeholder="标签（如：GPU 直通）" />
                    <a-button danger size="small" @click="delMetric(ci, mi)">✕</a-button>
                  </div>
                  <button type="button" class="dashed-add sm" @click="addMetric(ci)">＋ 添加数字</button>
                </div>
              </div>
              <!-- ＋ 添加维度（虚线尾卡） -->
              <div class="cap-ed cap-ed-add" @click="addCap">
                <span class="ecfg-add-icon">＋</span>
                <span class="ecfg-add-text">添加维度</span>
              </div>
            </div>

            <div class="sec-label">场景适配<span class="sec-hint">缩略图上传/更换 · ⧉ 复制链接 · 图下输入框粘贴链接</span></div>
            <div class="scn-grid">
              <div v-for="(s, i) in scnRows" :key="i" class="scn-card">
                <a-upload :before-upload="(f: any) => uploadScnImage(i, f)" :show-upload-list="false" accept="image/*">
                  <button type="button" class="scn-thumb" title="上传/更换配图">
                    <img v-if="s.image" :src="s.image" alt="" />
                    <span v-else class="scn-thumb-ph">配图</span>
                    <span class="up">⇪</span>
                    <span v-if="s.image" class="scn-copy" title="复制图片链接" @click.stop.prevent="copyScnUrl(s)">⧉</span>
                  </button>
                </a-upload>
                <a-input v-model:value="s.image" size="small" allowClear placeholder="图片链接，可粘贴" />
                <div class="scn-name-row">
                  <a-auto-complete v-model:value="s.name" class="kv-flex" :options="scnNameOptions"
                    placeholder="场景名（可联想其他机型已用）" allowClear />
                  <a-button danger size="small" @click="delScn(i)">✕</a-button>
                </div>
                <a-input v-model:value="s.fit" placeholder="一句话讲为什么适配（如：训推同平台，模型迭代不停机切换）" />
              </div>
              <!-- ＋ 添加场景（虚线卡，与关联配置同语言） -->
              <div class="scn-card scn-card-add" @click="addScn">
                <span class="ecfg-add-icon">＋</span>
                <span class="ecfg-add-text">添加场景</span>
              </div>
            </div>

            <div class="sec-label">完整技术规格<span class="sec-hint">详情页沉底折叠 · 参数都在这里</span></div>
            <div class="kv-list">
              <div v-for="(s, i) in form.product_content.specs" :key="i" class="kv-row">
                <a-input v-model:value="s.key" style="width:160px" placeholder="规格名（如 CPU）" />
                <a-textarea v-model:value="s.value" class="kv-flex" :autosize="{ minRows: 1, maxRows: 6 }" placeholder="规格值（支持换行）" />
                <a-button danger size="small" @click="delSpec(i)">✕</a-button>
              </div>
              <button type="button" class="dashed-add" @click="addSpec">＋ 添加规格</button>
            </div>
          </a-form>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<style scoped>
.editor-page { min-height: calc(100vh - var(--cpq-header-clearance, 0px)); }
.content-inner { width: 100%; margin: 0 auto; padding: 24px; }
.cfg-bar {
  /* 吸顶：页面很长，滚动中随时可保存/返回（main-scroll 是滚动容器） */
  position: sticky; top: calc(var(--cpq-sticky-top, 0px) + 8px); z-index: 30;
  display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; margin-bottom: 16px;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.18);
}
.cfg-bar-left { display: flex; align-items: center; gap: 16px; }
.cfg-title { margin: 0; font-size: 16px; }
.title-sub { color: var(--cpq-text-muted, #6E7582); font-weight: 400; font-size: 13px; }
.cfg-bar-right { display: flex; gap: 8px; }
.btn-ghost { background: transparent; border: 1px solid var(--cpq-overlay-w15); }

.single-col { padding: 16px 20px; }
.sec-label { font-size: 13px; font-weight: 600; color: var(--cpq-text-secondary, #9BA1AA); margin: 20px 0 8px; display: flex; justify-content: space-between; align-items: center; }
.sec-label:first-child { margin-top: 0; }
.sec-hint { font-size: 12px; font-weight: 400; color: var(--cpq-text-muted, #6E7582); }
.pub-hint { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); }

/* 关联基准配置（配置变体·卡片网格） */
.cfg-card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.ecfg-card { display: flex; flex-direction: column; gap: 6px; padding: 14px; border-radius: 12px; background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w10); }
.ecfg-card-head { display: flex; justify-content: space-between; align-items: center; }
.ecfg-badge { font-size: 11px; color: #1f9d6b; }
.ecfg-name { font-size: 14px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.ecfg-spec { font-size: 12px; color: var(--cpq-text-muted, #6E7582); }
.ecfg-actions { display: flex; gap: 2px; margin-top: 2px; }
.ecfg-content-edit { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--cpq-overlay-w15); }
.ecfg-content-foot { display: flex; justify-content: flex-end; }
.ecfg-card-add { align-items: center; justify-content: center; min-height: 96px; cursor: pointer; border-style: dashed; color: var(--cpq-text-muted, #6E7582); transition: all .2s; }
.ecfg-card-add:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.ecfg-add-icon { font-size: 28px; font-weight: 300; line-height: 1; }
.ecfg-add-text { font-size: 13px; }

/* 选择基准配置面板 */
.link-cfg-list { display: flex; flex-direction: column; gap: 8px; max-height: 50vh; overflow-y: auto; }
.link-cfg-item { padding: 12px 14px; border-radius: 10px; background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w10); cursor: pointer; transition: all .15s; }
.link-cfg-item:hover { border-color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10, rgba(22,119,255,.08)); }
.link-cfg-name { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.link-cfg-spec { font-size: 12px; color: var(--cpq-text-muted, #6E7582); margin-top: 2px; }

.img-row { display: flex; gap: 8px; align-items: center; }
.img-preview { margin-top: 8px; max-height: 120px; border-radius: 6px; border: 1px solid var(--cpq-overlay-w15); }
.hl-editor-layout { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 12px; align-items: start; }
.hl-editor-photo { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.hl-editor-photo :deep(.ant-upload-select) { display: block; width: 100%; }
.hl-photo-drop {
  position: relative; display: block; width: 100%; aspect-ratio: 1 / 1;
  border-radius: 12px; overflow: hidden; cursor: pointer; padding: 0;
  border: 1px dashed var(--cpq-overlay-w25, rgba(255, 255, 255, 0.25));
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.04));
}
.hl-photo-drop:hover { border-color: var(--cpq-accent-primary, #1677FF); }
.hl-photo-drop img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hl-photo-drop-ph { display: flex; width: 100%; height: 100%; align-items: center; justify-content: center; font-size: 12px; color: var(--cpq-text-muted, #6E7582); }
.hl-photo-drop .up {
  position: absolute; right: 6px; top: 6px; width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font-size: 14px;
  color: #fff; background: rgba(0, 0, 0, 0.55);
}

.kv-list { display: flex; flex-direction: column; gap: 8px; }
.kv-row { display: flex; gap: 8px; align-items: flex-start; }
.kv-flex { flex: 1; min-width: 0; }
.empty-hint { font-size: 13px; color: var(--cpq-text-muted, #6E7582); font-style: italic; padding: 6px 0; }

.sec-label-ops { display: inline-flex; gap: 2px; }
.sec-label-ops + .sec-hint { margin-left: 0; }
.pub-cell { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-height: 32px; }

/* 卡片化网格：亮点半宽两列 / 能力双列卡（镜像详情页一行两卡）/ 场景卡（图+链接+名+一句话） */
.hl-grid { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.hl-card { display: flex; gap: 8px; align-items: center; padding: 10px 12px; border-radius: 12px; background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w10); }
.hl-card-add { justify-content: center; min-height: 56px; cursor: pointer; border-style: dashed; color: var(--cpq-text-muted, #6E7582); transition: all .2s; }
.hl-card-add:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.cap-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(430px, 1fr)); gap: 12px; }
.cap-ed-add { align-items: center; justify-content: center; min-height: 140px; cursor: pointer; border-style: dashed; color: var(--cpq-text-muted, #6E7582); transition: all .2s; }
.cap-ed-add:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.dashed-add {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; min-height: 44px; padding: 0 12px;
  border-radius: 10px; border: 1px dashed var(--cpq-overlay-w30, rgba(255, 255, 255, 0.3));
  background: transparent; color: var(--cpq-text-muted, #6E7582);
  font-size: 13px; cursor: pointer; transition: all .2s;
}
.dashed-add.sm { min-height: 34px; font-size: 12px; }
.dashed-add:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.scn-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.scn-card {
  display: flex; flex-direction: column; gap: 6px;
  padding: 12px; border-radius: 12px;
  background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w10);
}
/* antd 的 .ant-upload-select 是 inline-block，会 shrink-wrap 包不住 width:100% 的缩略图按钮——强制撑满卡宽 */
.scn-card :deep(.ant-upload-select) { display: block; width: 100%; }
.scn-card-add { align-items: center; justify-content: center; min-height: 220px; cursor: pointer; border-style: dashed; color: var(--cpq-text-muted, #6E7582); transition: all .2s; }
.scn-card-add:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.scn-name-row { display: flex; gap: 6px; align-items: center; }

/* 能力板块编辑卡（双列网格内，镜像详情页能力卡结构：维度名/图标/一句话/关键数字） */
.cap-ed {
  display: flex; flex-direction: column; gap: 10px;
  padding: 14px 16px; border-radius: 12px;
  background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w10);
}
.cap-ed-head { display: flex; gap: 8px; align-items: center; }
.cap-ed-metrics { display: flex; flex-direction: column; gap: 6px; }
.cap-ed-metrics-label { font-size: 12px; font-weight: 600; color: var(--cpq-text-secondary, #9BA1AA); }

/* 图标选择条：一行 9 个发丝线图标，选中亮起（指示灯回落酒红） */
.ico-pick { display: flex; gap: 6px; flex-wrap: wrap; }
.ico-btn {
  width: 46px; height: 38px; padding: 2px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: 1px solid var(--cpq-overlay-w15); border-radius: 8px;
  color: var(--cpq-text-secondary, #9BA1AA); cursor: pointer; transition: all 0.15s;
}
.ico-btn :deep(svg) { width: 34px; height: auto; display: block; }
.ico-btn:hover { border-color: var(--cpq-overlay-w30, rgba(255, 255, 255, 0.3)); color: var(--cpq-text-primary, #E8ECEF); }
.ico-btn.on { color: var(--cpq-text-primary, #E8ECEF); border-color: #FF7A4D; box-shadow: 0 0 0 1px rgba(255, 122, 77, 0.35); }

/* 场景卡：图在上（上传/更换，⧉ 复制链接）→ 图下链接输入框 → 场景名联想 + ✕ → 一句话 */
.scn-copy {
  position: absolute; top: 3px; right: 3px;
  width: 18px; height: 18px; border-radius: 5px;
  background: rgba(0, 0, 0, 0.55); color: rgba(255, 255, 255, 0.9);
  font-size: 11px; line-height: 1;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; opacity: 0; transition: opacity 0.15s;
}
.scn-thumb:hover .scn-copy { opacity: 1; }
.scn-copy:hover { background: rgba(0, 0, 0, 0.8); color: #fff; }
.scn-thumb {
  position: relative; width: 100%; height: 96px;
  border-radius: 6px; overflow: hidden; cursor: pointer; padding: 0;
  border: 1px dashed var(--cpq-overlay-w30, rgba(255, 255, 255, 0.3));
  background: var(--cpq-overlay-w4); transition: border-color 0.15s;
}
.scn-thumb:hover { border-color: var(--cpq-accent-primary, #1677FF); }
.scn-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.scn-thumb-ph { display: flex; width: 100%; height: 100%; align-items: center; justify-content: center; font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.scn-thumb .up {
  position: absolute; right: 2px; bottom: 2px;
  font-size: 10px; line-height: 1; padding: 2px 4px; border-radius: 4px;
  background: rgba(0, 0, 0, 0.55); color: #fff;
}
</style>

@media (max-width: 640px) {
  .hl-editor-layout { grid-template-columns: 1fr; }
}
