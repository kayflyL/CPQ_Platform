<script setup lang="ts">
/** 机型管理（管理面）— 维护 server_models，给配置面「机型目录」供数。
 *  与「基准配置」相互独立；可选拉一个基准配置（BOM）挂在机型上。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { catalogApi, baseConfigApi, type ServerType, type ServerModel, type BaseConfig } from '@/api/serverConfig'

const models = ref<ServerModel[]>([])
const types = ref<ServerType[]>([])
const baseConfigs = ref<BaseConfig[]>([])
const typeFilter = ref<number | 'all'>('all')
const search = ref('')
const loading = ref(false)
const modalVisible = ref(false)
const editing = ref<ServerModel | null>(null)
const form = ref<Partial<ServerModel>>({})

const typeName = (id?: number) => types.value.find(t => t.id === id)?.name || '—'
const baseName = (id?: number) => baseConfigs.value.find(b => b.id === id)?.name || '—'

async function load() {
  loading.value = true
  try {
    const [typesRes, modelsRes, baseRes] = await Promise.all([
      catalogApi.listTypes(), catalogApi.listModels(), baseConfigApi.list(),
    ])
    types.value = typesRes.types
    models.value = modelsRes.models
    baseConfigs.value = baseRes.configs
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  let r = models.value
  if (typeFilter.value !== 'all') r = r.filter(m => m.server_type_id === typeFilter.value)
  if (search.value) r = r.filter(m => m.name.includes(search.value))
  return r
})

function openNew() {
  editing.value = null
  form.value = { server_type_id: types.value[0]?.id, form: '2U', bays: 12 }
  modalVisible.value = true
}
function openEdit(m: ServerModel) {
  editing.value = m
  form.value = { ...m }
  modalVisible.value = true
}
async function save() {
  if (!form.value.name) return message.warning('请填机型名')
  try {
    const payload: Partial<ServerModel> = {
      name: form.value.name,
      server_type_id: form.value.server_type_id,
      form: form.value.form,
      bays: form.value.bays,
      use: form.value.use,
      base_config_id: form.value.base_config_id,
    }
    if (editing.value) await catalogApi.updateModel(editing.value.id, payload)
    else await catalogApi.createModel(payload)
    message.success((editing.value ? '已更新' : '已新建') + '机型「' + form.value.name + '」')
    modalVisible.value = false
    load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}
async function remove(id: number, name: string) {
  await catalogApi.deleteModel(id); message.success('已删除 ' + name); load()
}

const columns = [
  { title: '机型名', dataIndex: 'name', key: 'name' },
  { title: '类型', key: 'type', width: 110 },
  { title: '形态', dataIndex: 'form', key: 'form', width: 70 },
  { title: '盘位', dataIndex: 'bays', key: 'bays', width: 70 },
  { title: '用途', dataIndex: 'use', key: 'use', ellipsis: true },
  { title: '关联基准配置', key: 'base', ellipsis: true },
  { title: '操作', key: 'op', width: 130 },
]
onMounted(load)
</script>

<template>
  <div class="model-manager panel glass">
    <div class="lib-head">
      <h3>机型管理</h3>
      <a-space>
        <a-select v-model:value="typeFilter" style="width:160px" size="small">
          <a-select-option value="all">全部类型</a-select-option>
          <a-select-option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
        </a-select>
        <a-input-search v-model:value="search" placeholder="搜机型名" style="width:180px" size="small" allowClear />
        <a-button type="primary" size="small" @click="openNew">+ 新建机型</a-button>
      </a-space>
    </div>
    <a-table :data-source="filtered" :columns="columns" :loading="loading" row-key="id" size="small"
             :pagination="{ pageSize: 15, size: 'small' }">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'type'">{{ typeName(record.server_type_id) }}</template>
        <template v-else-if="column.key === 'base'">{{ record.base_config_id ? baseName(record.base_config_id) : '—' }}</template>
        <template v-else-if="column.key === 'op'">
          <a-button size="small" link @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="删除该机型？" @confirm="remove(record.id, record.name)">
            <a-button size="small" link danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <a-modal :open="modalVisible" :title="editing ? '编辑机型' : '新建机型'" @ok="save"
             @cancel="modalVisible = false" width="620px" :destroyOnClose="true">
      <a-form layout="vertical">
        <a-form-item label="机型名" required><a-input v-model:value="form.name" placeholder="如 ES22V3-P" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="类型" required>
              <a-select v-model:value="form.server_type_id">
                <a-select-option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="形态">
              <a-select v-model:value="form.form">
                <a-select-option value="2U">2U</a-select-option>
                <a-select-option value="4U">4U</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8"><a-form-item label="盘位"><a-input-number v-model:value="form.bays" :min="1" style="width:100%" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="用途"><a-input v-model:value="form.use" placeholder="如 通用场景（可选）" /></a-form-item>
        <a-form-item label="关联基准配置">
          <a-select v-model:value="form.base_config_id" allowClear show-search optionFilterProp="label" placeholder="可选拉一个基准配置（BOM）">
            <a-select-option v-for="b in baseConfigs" :key="b.id" :value="b.id" :label="b.name">
              {{ b.name }}（{{ b.series || '—' }}·{{ b.form || '—' }}·{{ b.bays ?? '—' }}盘）
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.lib-head h3 { margin: 0; font-size: 15px; }
</style>
