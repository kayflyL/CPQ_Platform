<script setup lang="ts">
/** 机型管理（管理面）— 机型列表卡片网格。
 *  新建/编辑跳独立编辑页 ModelEditorPage（产品化包装），本组件只做列表 + 删除。
 *  机型技术参数（form/bays/series）从关联基准配置继承，JSONB 透传存 product_content。 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { catalogApi, baseConfigApi, type ServerType, type ServerModel, type BaseConfig } from '@/api/serverConfig'

type LifecycleStatus = 'new' | 'active' | 'eol' | 'discontinued'
const LIFECYCLES: { value: LifecycleStatus; label: string; chip: string }[] = [
  { value: 'new', label: '新品', chip: 'lc-new' },
  { value: 'active', label: '在售', chip: 'lc-active' },
  { value: 'eol', label: '即将停产', chip: 'lc-eol' },
  { value: 'discontinued', label: '停产', chip: 'lc-off' },
]
const lcMeta = (s?: string | null) => LIFECYCLES.find(l => l.value === s) || LIFECYCLES[1]

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
        <div v-for="m in filtered" :key="m.id" class="model-card">
          <span class="lc-chip" :class="lcMeta(m.lifecycle_status).chip">{{ lcMeta(m.lifecycle_status).label }}</span>
          <div class="m-thumb">
            <img v-if="m.image_url" :src="m.image_url" :alt="m.name" />
            <span v-else class="m-thumb-ph">机</span>
          </div>
          <div class="m-name">{{ m.name }}</div>
          <div class="m-type">{{ typeName(m.server_type_id) }}</div>
          <div class="m-specs">
            <span><i>形态</i>{{ m.base_config?.form || '—' }}</span>
            <span><i>盘位</i>{{ m.base_config?.bays ?? '—' }}</span>
            <span><i>系列</i>{{ m.base_config?.series || '—' }}</span>
          </div>
          <div class="m-bc" v-if="baseName(m.base_config_id)">基准配置 · {{ baseName(m.base_config_id) }}</div>
          <div class="m-bc m-bc-empty" v-else>未关联基准配置</div>
          <div class="m-foot">
            <a-button size="small" link @click="goEdit(m)">编辑</a-button>
            <a-popconfirm title="删除该机型？" @confirm="remove(m.id, m.name)">
              <a-button size="small" link danger>删除</a-button>
            </a-popconfirm>
          </div>
        </div>
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
.model-card {
  position: relative; display: flex; flex-direction: column; gap: 8px; padding: 16px;
  border: 1px solid var(--cpq-overlay-w10); border-radius: 14px;
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(14px);
  box-shadow: 0 10px 30px var(--cpq-overlay-b20), inset 0 1px 0 var(--cpq-overlay-w15);
  transition: all .2s cubic-bezier(.16,1,.3,1);
}
.model-card:hover {
  border-color: var(--cpq-overlay-a30);
  transform: translateY(-2px);
  box-shadow: 0 16px 40px var(--cpq-shadow-color-strong), inset 0 1px 0 var(--cpq-overlay-w15);
}
.lc-chip { position: absolute; top: 12px; right: 12px; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; border: 1px solid transparent; }
.lc-active { color: #1f9d6b; background: rgba(125, 215, 170, .18); border-color: rgba(125, 215, 170, .45); }
.lc-new    { color: #2f7de1; background: rgba(150, 195, 250, .18); border-color: rgba(150, 195, 250, .45); }
.lc-eol    { color: #c8861a; background: rgba(245, 200, 110, .18); border-color: rgba(245, 200, 110, .45); }
.lc-off    { color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w6); border-color: var(--cpq-overlay-w15); }

.m-thumb { height: 92px; border-radius: 10px; overflow: hidden; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); display: flex; align-items: center; justify-content: center; }
.m-thumb img { width: 100%; height: 100%; object-fit: contain; }
.m-thumb-ph { font-size: 26px; font-weight: 700; color: var(--cpq-text-muted, #6E7582); opacity: .5; }
.m-name { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.m-type { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); }
.m-specs { display: flex; gap: 12px; padding: 8px 0; border-top: 1px solid var(--cpq-overlay-w10); }
.m-specs span { display: flex; flex-direction: column; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.m-specs i { font-size: 11px; font-weight: 400; font-style: normal; color: var(--cpq-text-muted, #6E7582); }
.m-bc { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); }
.m-bc-empty { color: var(--cpq-text-muted, #6E7582); font-style: italic; }
.m-desc { font-size: 12px; line-height: 1.5; color: var(--cpq-text-secondary, #9BA1AA); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 18px; }
.m-foot { display: flex; justify-content: flex-end; gap: 4px; margin-top: 2px; }
</style>
