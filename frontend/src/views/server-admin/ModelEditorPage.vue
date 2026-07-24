<script setup lang="ts">
/** 机型产品化包装编辑页（管理面，单栏流式）。
 *  基本信息 + 主图 + 产品内容（概述/应用场景/核心特性/产品规格）。
 *  路由复用：/servers/models/new 与 /servers/models/:modelId/edit 同一组件。 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import axios from 'axios'
import {
  catalogApi, baseConfigApi,
  type ServerType, type ServerModel, type BaseConfig, type ModelProductContent,
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
const baseConfigs = ref<BaseConfig[]>([])
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

/** 选中基准配置后即时映射继承到的技术参数（只读展示）。 */
const inheritedSpecs = computed(() => {
  const id = form.value.base_config_id
  const fromList = baseConfigs.value.find(b => b.id === id)
  if (fromList) return { form: fromList.form, bays: fromList.bays, series: fromList.series }
  return { form: undefined, bays: undefined, series: undefined }
})

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
    const [typesRes, baseRes, modelsRes] = await Promise.all([
      catalogApi.listTypes(), baseConfigApi.list(), catalogApi.listModels(),
    ])
    types.value = typesRes.types
    baseConfigs.value = baseRes.configs
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
    if (editingId.value) await catalogApi.updateModel(editingId.value, payload)
    else await catalogApi.createModel(payload)
    message.success((editingId.value ? '已更新' : '已新建') + '机型「' + form.value.name + '」')
    router.push({ path: '/servers/admin', query: { refresh: 'models' } })
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
            <a-form-item label="关联基准配置" help="机型的形态/盘位/系列从基准配置继承，选中后只读展示">
              <a-select v-model:value="form.base_config_id" allowClear show-search optionFilterProp="label" placeholder="选一个基准配置（BOM）">
                <a-select-option v-for="b in baseConfigs" :key="b.id" :value="b.id" :label="b.name">
                  {{ b.name }}（{{ b.series || '—' }}·{{ b.form || '—' }}·{{ b.bays ?? '—' }}盘）
                </a-select-option>
              </a-select>
            </a-form-item>
            <div class="inherited" v-if="form.base_config_id">
              <span class="inh-k">继承参数</span>
              <span class="inh-v">形态 <b>{{ inheritedSpecs.form || '—' }}</b></span>
              <span class="inh-v">盘位 <b>{{ inheritedSpecs.bays ?? '—' }}</b></span>
              <span class="inh-v">系列 <b>{{ inheritedSpecs.series || '—' }}</b></span>
            </div>

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

.inherited { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; padding: 8px 12px; margin-bottom: 12px; border-radius: 8px; background: var(--cpq-overlay-w4); border: 1px dashed var(--cpq-overlay-w15); }
.inherited .inh-k { font-size: 12px; color: var(--cpq-text-muted, #6E7582); }
.inherited .inh-v { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); }
.inherited .inh-v b { color: var(--cpq-text-primary, #E8ECEF); font-weight: 600; }

.img-row { display: flex; gap: 8px; align-items: center; }
.img-preview { margin-top: 8px; max-height: 120px; border-radius: 6px; border: 1px solid var(--cpq-overlay-w15); }

.kv-list { display: flex; flex-direction: column; gap: 8px; }
.kv-row { display: flex; gap: 8px; align-items: flex-start; }
.kv-flex { flex: 1; min-width: 0; }
.empty-hint { font-size: 13px; color: var(--cpq-text-muted, #6E7582); font-style: italic; padding: 6px 0; }
</style>
