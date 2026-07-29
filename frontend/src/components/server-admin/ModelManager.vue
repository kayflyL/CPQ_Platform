<script setup lang="ts">
/** 机型管理（管理面）— 机型列表卡片网格。
 *  新建/编辑跳独立编辑页 ModelEditorPage（产品化包装），本组件只做列表 + 删除。
 *  机型技术参数（form/bays/series）从关联基准配置继承，JSONB 透传存 product_content。 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { catalogApi, baseConfigApi, type ServerType, type ServerModel, type BaseConfig } from '@/api/serverConfig'
import ServerModelCard from '@/components/common/ServerModelCard.vue'

const route = useRoute()
const router = useRouter()

const models = ref<ServerModel[]>([])
const types = ref<ServerType[]>([])
const baseConfigs = ref<BaseConfig[]>([])
const typeFilter = ref<number | 'all'>('all')
const search = ref('')
const loading = ref(false)

const typeName = (id?: number) => types.value.find(t => t.id === id)?.name || '—'
const baseName = (id?: number) => baseConfigs.value.find(b => b.id === id)?.name

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

function goNew() { router.push('/servers/models/new') }
function goEdit(m: ServerModel) { router.push(`/servers/models/${m.id}/edit`) }
async function remove(id: number, name: string) {
  await catalogApi.deleteModel(id)
  message.success('已删除 ' + name)
  load()
}

onMounted(load)
/** 编辑页保存返回（?refresh=models）后刷新列表。 */
watch(() => route.query.refresh, (v) => { if (v === 'models') load() })
</script>

<template>
  <div class="model-manager panel glass">
    <div class="lib-head">
      <h3>机型管理</h3>
      <a-space>
        <a-select v-model:value="typeFilter" style="width:160px" size="small" placeholder="全部类型">
          <a-select-option value="all">全部类型</a-select-option>
          <a-select-option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
        </a-select>
        <a-input-search v-model:value="search" placeholder="搜机型名" style="width:180px" size="small" allowClear />
        <a-button type="primary" size="small" @click="goNew">+ 新建机型</a-button>
      </a-space>
    </div>

    <a-spin :spinning="loading">
      <div v-if="filtered.length" class="model-grid">
        <ServerModelCard
          v-for="m in filtered"
          :key="m.id"
          :model="m"
          :type-name="typeName(m.server_type_id)"
          :base-config-name="baseName(m.base_config_id)"
          :show-actions="true"
          :clickable="false"
          @edit="goEdit(m)"
          @delete="remove(m.id, m.name)"
        />
      </div>
      <a-empty v-else description="暂无机型，点「新建机型」添加" />
    </a-spin>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.lib-head h3 { margin: 0; font-size: 15px; }

.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(248px, 1fr)); gap: 16px; }
</style>
