<script setup lang="ts">
/** 服务器3D模型管理 · 目录页 — 卡片列表(ServerModelCard 同款);点卡片进模型编辑页。
 *  3D模型由代码/种子产出,页面只做编辑(名称/绑定/分区标注),不提供网页新建。
 *  模型页(独立路由 /servers/3d-models/:id):名称/多选绑定机型/分区标注/3D预览。 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { server3dApi, type Server3dModel } from '@/api/server3d'
import { catalogApi } from '@/api/serverConfig'
import ServerModelCard from '@/components/common/ServerModelCard.vue'

const router = useRouter()
const loading = ref(false)
const models = ref<Server3dModel[]>([])
const modelNames = ref<Record<number, string>>({})

const boundLabel = (m: Server3dModel) => {
  const ids = m.model_ids || []
  if (!ids.length) return '未关联机型(配置页不显示)'
  const first = modelNames.value[ids[0]] || `机型#${ids[0]}`
  return ids.length === 1 ? `关联机型 · ${first}` : `关联机型 · ${first} 等 ${ids.length} 台`
}
function goEdit(m: Server3dModel) {
  router.push(`/servers/3d-models/${m.id}`)
}
/** 塞进 ServerModelCard 的最小机型形状(仅展示字段) */
const toCardModel = (m: Server3dModel) => ({
  id: m.id,
  name: m.name,
  is_published: true,
  lifecycle_status: undefined,
})

async function load() {
  loading.value = true
  try {
    const [list, res] = await Promise.all([server3dApi.list(), catalogApi.listModels().catch(() => ({ models: [] as any[] }))])
    models.value = list
    const map: Record<number, string> = {}
    for (const m of (res as any).models || []) map[m.id] = m.name
    modelNames.value = map
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '3D模型加载失败')
  } finally {
    loading.value = false
  }
}

function remove(m: Server3dModel) {
  Modal.confirm({
    title: `删除3D模型「${m.name}」?`,
    content: '仅删除3D登记与机型绑定,不影响机型本身与图纸。',
    okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      try {
        await server3dApi.remove(m.id)
        message.success('已删除')
        await load()
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '删除失败')
      }
    },
  })
}

onMounted(load)
</script>

<template>
  <div class="s3dm-root">
    <div class="s3dm-head">
      <div>
        <h3 class="s3dm-title">服务器3D模型管理</h3>
        <p class="s3dm-sub">参数化3D配置台的模型登记:点卡片进入模型页,关联具体服务器产品后,配置页中部即以3D场景替代2D图纸。</p>
      </div>
    </div>
    <a-spin :spinning="loading">
      <div class="s3dm-grid">
        <ServerModelCard
          v-for="m in models"
          :key="m.id"
          :model="toCardModel(m)"
          :type-name="boundLabel(m)"
          :show-image="false"
          :show-lifecycle="false"
          :show-specs="false"
          :show-tagline="false"
          :show-base-config="false"
          :show-actions="true"
          :show-publish="false"
          :clickable="true"
          @click="goEdit(m)"
          @edit="goEdit(m)"
          @delete="remove(m)"
        />
      </div>
    </a-spin>
  </div>
</template>

<style scoped>
.s3dm-root {
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-4);
}
.s3dm-title {
  margin: 0;
  font-size: var(--cpq-font-size-lg);
  font-weight: 700;
}
.s3dm-sub {
  margin: var(--cpq-space-1) 0 0;
  color: var(--cpq-text-secondary);
  font-size: var(--cpq-font-size-sm);
}
.s3dm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(252px, 1fr));
  gap: 16px;
}
</style>
