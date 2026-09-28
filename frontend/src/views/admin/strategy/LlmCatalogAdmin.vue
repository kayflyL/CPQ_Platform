<script setup lang="ts">
defineOptions({ name: 'LlmCatalogAdmin' })
/** 智算模型库管理（策略中心·解决方案域）：大模型库/推理框架库/场景参数表 三卡行编辑（admin-card-pattern）。
 *  数据 = rules 三软库；首版导入已走 dry_run+确认，此处日常增删改；框架系数可调（不写死）。 */
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { gpuCatalogAdminApi, type LlmModelRow, type FrameworkRow, type SceneRow } from '@/api/gpuSizing'

const tab = ref('models')
const models = ref<LlmModelRow[]>([])
const frameworks = ref<FrameworkRow[]>([])
const scenes = ref<SceneRow[]>([])
const loading = ref(false)

const ATTN_OPTS = ['GQA', 'MHA', 'MLA'].map(v => ({ value: v, label: v }))
const CONF_OPTS = [{ value: 'high', label: '高' }, { value: 'mid', label: '中' }, { value: 'low', label: '低' }]

const modelModal = ref(false)
const fwModal = ref(false)
const sceneModal = ref(false)
const editingId = ref<number | null>(null)
const mForm = reactive<Partial<LlmModelRow>>({})
const fForm = reactive<Partial<FrameworkRow>>({})
const sForm = reactive<Partial<SceneRow>>({})

async function load() {
  loading.value = true
  try {
    const [a, b, c] = await Promise.all([gpuCatalogAdminApi.models(), gpuCatalogAdminApi.frameworks(), gpuCatalogAdminApi.scenes()])
    models.value = a.models; frameworks.value = b.frameworks; scenes.value = c.scenes
  } catch (e: any) { message.error(e.response?.data?.detail || '加载失败') } finally { loading.value = false }
}
onMounted(load)

function openModel(row?: LlmModelRow) {
  editingId.value = row?.id ?? null
  Object.assign(mForm, row || { vendor: '', name: '', params_b: undefined, default_bits: 4, attn: 'GQA', confidence: 'mid' })
  modelModal.value = true
}
async function saveModel() {
  try {
    if (editingId.value) await gpuCatalogAdminApi.updateModel(editingId.value, mForm)
    else await gpuCatalogAdminApi.createModel(mForm)
    message.success('已保存'); modelModal.value = false; await load()
  } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
}
async function removeModel(r: LlmModelRow) {
  await gpuCatalogAdminApi.removeModel(r.id); message.success('已删除 ' + r.name); await load()
}

function openFw(row?: FrameworkRow) {
  editingId.value = row?.id ?? null
  Object.assign(fForm, row || { name: '', default_quant: '4bit(AWQ)', coeff_4bit: 1.05, coeff_8bit: 1, coeff_16bit: 1, overhead_gb: 1, tensor_parallel: true })
  fwModal.value = true
}
async function saveFw() {
  try {
    if (editingId.value) await gpuCatalogAdminApi.updateFramework(editingId.value, fForm)
    else await gpuCatalogAdminApi.createFramework(fForm)
    message.success('已保存'); fwModal.value = false; await load()
  } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
}
async function removeFw(r: FrameworkRow) {
  await gpuCatalogAdminApi.removeFramework(r.id); message.success('已删除 ' + r.name); await load()
}

function openScene(row?: SceneRow) {
  editingId.value = row?.id ?? null
  Object.assign(sForm, row || { name: '', recommend_ctx: 8192, min_tok_s: 5, need_vision: false })
  sceneModal.value = true
}
async function saveScene() {
  try {
    if (editingId.value) await gpuCatalogAdminApi.updateScene(editingId.value, sForm)
    else await gpuCatalogAdminApi.createScene(sForm)
    message.success('已保存'); sceneModal.value = false; await load()
  } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
}
async function removeScene(r: SceneRow) {
  await gpuCatalogAdminApi.removeScene(r.id); message.success('已删除 ' + r.name); await load()
}
</script>

<template>
  <div class="lca">
    <header class="lca-head">
      <div>
        <h2 class="lca-title">模型与参数库</h2>
        <p class="lca-sub">AI 推理配置器的三张参考库。框架系数随版本漂移，改即生效；结构四参数缺一不可算。</p>
      </div>
    </header>

    <a-tabs v-model:activeKey="tab" class="lca-tabs">
      <a-tab-pane key="models" tab="大模型库">
        <div class="lca-chead">
          <span class="lca-count">共 {{ models.length }} 个模型</span>
          <a-button type="primary" size="small" @click="openModel()">+ 新增模型</a-button>
        </div>
        <a-table :data-source="models" :loading="loading" row-key="id" size="small" :pagination="{ pageSize: 12 }"
                 :columns="[
                   { title: '公司', dataIndex: 'vendor', width: 90 },
                   { title: '模型', dataIndex: 'name' },
                   { title: '参数(B)', dataIndex: 'params_b', width: 80 },
                   { title: '注意力', dataIndex: 'attn', width: 80 },
                   { title: '结构(hidden/layers/heads/kv)', key: 'struct', width: 190 },
                   { title: '原生ctx', key: 'ctx', width: 80 },
                   { title: '置信度', key: 'conf', width: 70 },
                   { title: '操作', key: 'op', width: 110 }]">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'struct'">{{ record.hidden_dim }} / {{ record.num_layers }} / {{ record.num_heads }} / {{ record.kv_heads }}</template>
            <template v-else-if="column.key === 'ctx'"><span>{{ record.max_ctx ? record.max_ctx / 1024 + 'K' : '—' }}</span></template>
            <template v-else-if="column.key === 'conf'"><span :class="record.confidence === 'high' ? 'lca-ok' : 'lca-mid'">{{ record.confidence }}</span></template>
            <template v-else-if="column.key === 'op'">
              <a-button size="small" link @click="openModel(record)">编辑</a-button>
              <a-popconfirm title="删除该模型？" @confirm="removeModel(record)"><a-button size="small" link danger>删除</a-button></a-popconfirm>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="frameworks" tab="推理框架库">
        <div class="lca-chead">
          <span class="lca-count">共 {{ frameworks.length }} 个框架</span>
          <a-button type="primary" size="small" @click="openFw()">+ 新增框架</a-button>
        </div>
        <a-table :data-source="frameworks" row-key="id" size="small" :pagination="false"
                 :columns="[
                   { title: '框架', dataIndex: 'name', width: 130 },
                   { title: '默认量化', dataIndex: 'default_quant', width: 110 },
                   { title: '4bit系数', dataIndex: 'coeff_4bit', width: 80 },
                   { title: '8bit系数', dataIndex: 'coeff_8bit', width: 80 },
                   { title: '16bit系数', dataIndex: 'coeff_16bit', width: 85 },
                   { title: '额外开销(GB)', dataIndex: 'overhead_gb', width: 105 },
                   { title: '张量并行', key: 'tp', width: 80 },
                   { title: '操作', key: 'op', width: 110 }]">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'tp'"><span>{{ record.tensor_parallel ? '是' : '否' }}</span></template>
            <template v-else-if="column.key === 'op'">
              <a-button size="small" link @click="openFw(record)">编辑</a-button>
              <a-popconfirm title="删除该框架？" @confirm="removeFw(record)"><a-button size="small" link danger>删除</a-button></a-popconfirm>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="scenes" tab="场景参数">
        <div class="lca-chead">
          <span class="lca-count">共 {{ scenes.length }} 个场景</span>
          <a-button type="primary" size="small" @click="openScene()">+ 新增场景</a-button>
        </div>
        <a-table :data-source="scenes" row-key="id" size="small" :pagination="false"
                 :columns="[
                   { title: '场景', dataIndex: 'name' },
                   { title: '推荐上下文', key: 'ctx', width: 120 },
                   { title: '最低速度(tok/s)', dataIndex: 'min_tok_s', width: 130 },
                   { title: '需多模态', key: 'vision', width: 90 },
                   { title: '操作', key: 'op', width: 110 }]">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'ctx'"><span>{{ record.recommend_ctx ? record.recommend_ctx / 1024 + 'K' : '—' }}</span></template>
            <template v-else-if="column.key === 'vision'"><span>{{ record.need_vision ? '是' : '否' }}</span></template>
            <template v-else-if="column.key === 'op'">
              <a-button size="small" link @click="openScene(record)">编辑</a-button>
              <a-popconfirm title="删除该场景？" @confirm="removeScene(record)"><a-button size="small" link danger>删除</a-button></a-popconfirm>
            </template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <a-modal v-model:open="modelModal" :title="editingId ? '编辑模型' : '新增模型'" @ok="saveModel" destroy-on-close width="640px">
      <a-form layout="vertical" class="lca-form">
        <div class="lca-grid">
          <a-form-item label="公司" required><a-input v-model:value="mForm.vendor" /></a-form-item>
          <a-form-item label="模型名" required><a-input v-model:value="mForm.name" /></a-form-item>
          <a-form-item label="参数量(B)" required><a-input-number v-model:value="mForm.params_b" :min="0.1" style="width:100%" /></a-form-item>
          <a-form-item label="默认精度(bit)"><a-input-number v-model:value="mForm.default_bits" :min="1" style="width:100%" /></a-form-item>
          <a-form-item label="注意力类型"><a-select v-model:value="mForm.attn" :options="ATTN_OPTS" /></a-form-item>
          <a-form-item label="参数置信度"><a-select v-model:value="mForm.confidence" :options="CONF_OPTS" /></a-form-item>
          <a-form-item label="hidden_dim"><a-input-number v-model:value="mForm.hidden_dim" style="width:100%" /></a-form-item>
          <a-form-item label="num_layers"><a-input-number v-model:value="mForm.num_layers" style="width:100%" /></a-form-item>
          <a-form-item label="num_heads"><a-input-number v-model:value="mForm.num_heads" style="width:100%" /></a-form-item>
          <a-form-item label="kv_heads"><a-input-number v-model:value="mForm.kv_heads" style="width:100%" /></a-form-item>
          <a-form-item label="原生上下文上限(tokens)"><a-input-number v-model:value="mForm.max_ctx" :min="0" style="width:100%" /></a-form-item>
          <a-form-item label="实测大小(GB,可选)"><a-input-number v-model:value="mForm.measured_size_gb" :min="0" style="width:100%" /></a-form-item>
        </div>
        <a-form-item label="备注"><a-input v-model:value="mForm.note" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="fwModal" :title="editingId ? '编辑框架' : '新增框架'" @ok="saveFw" destroy-on-close width="560px">
      <a-form layout="vertical" class="lca-form">
        <div class="lca-grid">
          <a-form-item label="框架名" required><a-input v-model:value="fForm.name" /></a-form-item>
          <a-form-item label="默认量化"><a-input v-model:value="fForm.default_quant" /></a-form-item>
          <a-form-item label="4bit 系数"><a-input-number v-model:value="fForm.coeff_4bit" :step="0.01" style="width:100%" /></a-form-item>
          <a-form-item label="8bit 系数"><a-input-number v-model:value="fForm.coeff_8bit" :step="0.01" style="width:100%" /></a-form-item>
          <a-form-item label="16bit 系数"><a-input-number v-model:value="fForm.coeff_16bit" :step="0.01" style="width:100%" /></a-form-item>
          <a-form-item label="额外开销(GB/卡)"><a-input-number v-model:value="fForm.overhead_gb" :step="0.1" style="width:100%" /></a-form-item>
          <a-form-item label="支持张量并行"><a-switch v-model:checked="fForm.tensor_parallel" /></a-form-item>
        </div>
      </a-form>
    </a-modal>

    <a-modal v-model:open="sceneModal" :title="editingId ? '编辑场景' : '新增场景'" @ok="saveScene" destroy-on-close width="480px">
      <a-form layout="vertical" class="lca-form">
        <a-form-item label="场景名" required><a-input v-model:value="sForm.name" /></a-form-item>
        <a-form-item label="推荐上下文(tokens)"><a-input-number v-model:value="sForm.recommend_ctx" :min="1024" :step="1024" style="width:100%" /></a-form-item>
        <a-form-item label="最低速度(tok/s)"><a-input-number v-model:value="sForm.min_tok_s" :min="0" style="width:100%" /></a-form-item>
        <a-form-item label="需多模态"><a-switch v-model:checked="sForm.need_vision" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.lca { display: flex; flex-direction: column; }
.lca-title { font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); margin: 0 0 4px; }
.lca-sub { font-size: 12px; color: var(--cpq-text-muted); margin: 0 0 10px; }
.lca-tabs :deep(.ant-tabs-tab) { font-size: 13px; }
.lca-chead { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.lca-count { font-size: 12px; color: var(--cpq-text-muted); }
.lca-ok { color: #16a34a; font-weight: 600; }
.lca-mid { color: #d97706; }
.lca-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
</style>
