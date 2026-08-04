<script setup lang="ts">
/** 机型产品化包装编辑页（管理面，单栏流式）。
 *  基本信息 + 关联基准配置（一对多·配置变体）+ 主图 + 产品内容（概述/应用场景/核心特性/产品规格）。
 *  路由复用：/servers/models/new 与 /servers/models/:modelId/edit 同一组件。
 *  新建机型保存后留在本页（关联配置需要先有机型 id）。 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import axios from 'axios'
import {
  catalogApi, baseConfigApi,
  type ServerType, type ServerModel, type BaseConfig, type ModelProductContent, type ConfigContent,
} from '@/api/serverConfig'

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
  image_url?: string
  product_content: ModelProductContent
}>({
  lifecycle_status: 'active',
  product_content: { overview: '', features: [], specs: [], scenarios: [] },
})

const typeName = (id?: number) => types.value.find(t => t.id === id)?.name || '—'

/** 应用场景标签：a-select mode=tags 要求非空数组，computed 代理兜底。 */
const scenarios = computed({
  get: () => form.value.product_content.scenarios || [],
  set: (v: string[]) => { form.value.product_content.scenarios = v },
})

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

// ---- 产品内容：特性 / 规格增删 ----
function addFeature() { form.value.product_content.features?.push({ text: '' }) }
function delFeature(i: number) { form.value.product_content.features?.splice(i, 1) }
function addSpec() { form.value.product_content.specs?.push({ key: '', value: '' }) }
function delSpec(i: number) { form.value.product_content.specs?.splice(i, 1) }

// ---- 主图上传（复用既有端点 POST /api/server-catalog/models/image）----
async function handleImageUpload(file: File): Promise<boolean> {
  try {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await axios.post('/api/server-catalog/models/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    form.value.image_url = resp.data.url
    message.success('图片已上传')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  }
  return false
}

async function init() {
  loading.value = true
  try {
    const [typesRes, modelsRes] = await Promise.all([
      catalogApi.listTypes(), catalogApi.listModels(),
    ])
    types.value = typesRes.types
    // 跨机型收集应用场景历史标签（联想源）
    const set = new Set<string>()
    for (const m of modelsRes.models) {
      const sc = m.product_content?.scenarios
      if (Array.isArray(sc)) sc.forEach(s => s && set.add(s))
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
        image_url: m.image_url,
        product_content: {
          overview: pc?.overview || '',
          features: pc?.features || [],
          specs: pc?.specs || [],
          scenarios: Array.isArray(pc?.scenarios) ? [...pc!.scenarios!] : [],
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
      image_url: form.value.image_url,
      product_content: form.value.product_content,
    }
    if (editingId.value) {
      await catalogApi.updateModel(editingId.value, payload)
      message.success('已更新机型「' + form.value.name + '」')
      router.push({ path: '/servers/admin', query: { refresh: 'models' } })
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
function cancel() { router.push('/servers/admin') }

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
              <a-col :span="10"><a-form-item label="机型名" required><a-input v-model:value="form.name" placeholder="如 ES22V3-P" /></a-form-item></a-col>
              <a-col :span="8"><a-form-item label="类型" required>
                <a-select v-model:value="form.server_type_id">
                  <a-select-option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
                </a-select>
              </a-form-item></a-col>
              <a-col :span="6"><a-form-item label="生命周期">
                <a-select v-model:value="form.lifecycle_status">
                  <a-select-option v-for="l in LIFECYCLES" :key="l.value" :value="l.value">{{ l.label }}</a-select-option>
                </a-select>
              </a-form-item></a-col>
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

            <!-- 产品内容 -->
            <div class="sec-label">产品概述</div>
            <a-textarea v-model:value="form.product_content.overview" :rows="3" placeholder="面向客户的一段话产品介绍" />

            <div class="sec-label">应用场景<span class="sec-hint">输入后回车添加，可联想其他机型已用场景</span></div>
            <a-select v-model:value="scenarios" mode="tags" :options="scenarioOptions" style="width:100%" placeholder="如：云计算，回车添加" :token-separators="[',']" />

            <div class="sec-label">核心特性<a-button size="small" type="link" @click="addFeature">+ 添加</a-button></div>
            <div v-if="form.product_content.features?.length" class="kv-list">
              <div v-for="(f, i) in form.product_content.features" :key="i" class="kv-row">
                <a-input v-model:value="f.icon" style="width:90px" placeholder="图标" />
                <a-input v-model:value="f.text" class="kv-flex" placeholder="特性描述（如：双路 AMD EPCTX9000）" />
                <a-button danger size="small" @click="delFeature(i)">✕</a-button>
              </div>
            </div>
            <div v-else class="empty-hint">点「添加」录入核心卖点</div>

            <div class="sec-label">产品规格<a-button size="small" type="link" @click="addSpec">+ 添加</a-button></div>
            <div v-if="form.product_content.specs?.length" class="kv-list">
              <div v-for="(s, i) in form.product_content.specs" :key="i" class="kv-row">
                <a-input v-model:value="s.key" style="width:160px" placeholder="规格名（如 CPU）" />
                <a-textarea v-model:value="s.value" class="kv-flex" :autosize="{ minRows: 1, maxRows: 6 }" placeholder="规格值（支持换行）" />
                <a-button danger size="small" @click="delSpec(i)">✕</a-button>
              </div>
            </div>
            <div v-else class="empty-hint">点「添加」录入产品规格</div>
          </a-form>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<style scoped>
.editor-page { min-height: 100vh; }
.content-inner { width: 100%; margin: 0 auto; padding: 24px; }
.cfg-bar { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; margin-bottom: 16px; }
.cfg-bar-left { display: flex; align-items: center; gap: 16px; }
.cfg-title { margin: 0; font-size: 16px; }
.title-sub { color: var(--cpq-text-muted, #6E7582); font-weight: 400; font-size: 13px; }
.cfg-bar-right { display: flex; gap: 8px; }
.btn-ghost { background: transparent; border: 1px solid var(--cpq-overlay-w15); }

.single-col { padding: 16px 20px; }
.sec-label { font-size: 13px; font-weight: 600; color: var(--cpq-text-secondary, #9BA1AA); margin: 20px 0 8px; display: flex; justify-content: space-between; align-items: center; }
.sec-label:first-child { margin-top: 0; }
.sec-hint { font-size: 12px; font-weight: 400; color: var(--cpq-text-muted, #6E7582); }

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

.kv-list { display: flex; flex-direction: column; gap: 8px; }
.kv-row { display: flex; gap: 8px; align-items: flex-start; }
.kv-flex { flex: 1; min-width: 0; }
.empty-hint { font-size: 13px; color: var(--cpq-text-muted, #6E7582); font-style: italic; padding: 6px 0; }
</style>
