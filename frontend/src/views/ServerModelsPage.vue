<script setup lang="ts">
/** 机型目录页（/servers/types/:typeId）— 展示某类型下所有机型，点击进详情页。
 *  整页固定暗色（同详情页：自带 token，不引用 --cpq-* 主题变量），不受主题切换影响 */
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerType, type ServerModel } from '@/api/serverConfig'
import ModelShowcase from '@/components/server-config/ModelShowcase.vue'
import ServerModelCard from '@/components/common/ServerModelCard.vue'
import { getShowcaseConfig } from '@/components/server-config/showcase-config'

const route = useRoute()
const router = useRouter()

const typeId = computed(() => Number(route.params.typeId))
const currentType = ref<ServerType | null>(null)
const models = ref<ServerModel[]>([])
const loading = ref(false)
const showcaseConfig = computed(() =>
  currentType.value ? getShowcaseConfig(currentType.value) : null
)

async function loadTypeAndModels() {
  loading.value = true
  try {
    const typesRes = await catalogApi.listTypes()
    currentType.value = typesRes.types.find(t => t.id === typeId.value) || null

    const modelsRes = await catalogApi.listModels(typeId.value, { publishedOnly: true })
    models.value = modelsRes.models
  } catch (e: any) {
    console.error('加载机型失败', e)
  } finally { loading.value = false }
}

function goBack() {
  router.push('/servers')
}

function goToDetail(model: ServerModel) {
  router.push(`/servers/models/${model.id}`)
}

// 整页固定暗色垫在透明顶栏下：声明 hero-dark，顶栏切浅色文字（浅色主题下也可读）
function markHeroDark(on: boolean) {
  if (on) document.documentElement.dataset.heroDark = '1'
  else delete document.documentElement.dataset.heroDark
}

onMounted(() => {
  markHeroDark(true)
  loadTypeAndModels()
})
onBeforeUnmount(() => markHeroDark(false))
</script>

<template>
  <div class="models-page">
    <div class="page-inner">
      <!-- 面包屑导航 -->
      <div class="breadcrumb">
        <a-button type="text" @click="goBack" class="back-btn">
          <template #icon>
            <span style="font-size: 16px;">←</span>
          </template>
          返回服务器类型
        </a-button>
        <a-divider type="vertical" />
        <span class="current-type">{{ currentType?.name || '加载中...' }}</span>
      </div>

      <!-- 页面标题 -->
      <h2 class="page-title">{{ currentType?.name || '' }} · 机型目录</h2>
      <p class="page-desc">{{ currentType?.description || '' }}</p>

      <!-- 3D 机型总览（仅命中映射的分类渲染） -->
      <ModelShowcase v-if="showcaseConfig" :config="showcaseConfig" />

      <!-- 机型卡片网格 -->
      <div class="models-grid" v-if="models.length">
        <ServerModelCard
          v-for="m in models"
          :key="m.id"
          :model="m"
          :show-base-config="false"
          dark
          @click="goToDetail(m)"
        />
      </div>
      <div v-else-if="!loading" class="sc-empty">该类型下暂无机型，去「管理」添加。</div>
    </div>
  </div>
</template>

<style scoped>
/* 整页固定暗色（深海蓝，同详情页 ocean 系）：负 margin 垫到透明顶栏下，padding 等量补回 */
.models-page {
  margin-top: calc(-1 * var(--cpq-header-clearance, 0px));
  padding: calc(var(--cpq-header-clearance, 0px) + 4px) 0 80px;
  /* 满高：内容少（如类型下仅一两台机型）时也要盖住 .main-scroll 的主题渐变，不露浅色底。
     负 margin 已把页面顶到 y=0，min-height 直接取整视口 */
  min-height: 100vh;
  background: linear-gradient(to bottom, #02050f 0%, #071226 45%, #030814 100%);
  color: #eef3fa;
}
.page-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 24px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}
.back-btn {
  /* 固定暗色页脱离主题体系：!important 压过 antd 按钮文字 token（同详情页 .scene-back） */
  color: rgba(238, 243, 250, 0.72) !important;
  font-size: 14px;
  padding: 4px 8px;
}
.back-btn:hover {
  color: #8cbdff !important;
}
.current-type {
  color: #f2f8ff;
  font-size: 14px;
  font-weight: 500;
}
.models-page :deep(.ant-divider-vertical) {
  border-inline-start-color: rgba(255, 255, 255, 0.25);
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 4px;
  color: #f2f8ff;
}
.page-desc {
  color: rgba(238, 243, 250, 0.72);
  font-size: 14px;
  margin-bottom: 28px;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
}
.sc-empty {
  color: rgba(238, 243, 250, 0.52);
  text-align: center;
  padding: 60px 0;
  font-size: 14px;
}
@media (max-width: 640px) {
  .page-inner { padding: 0 12px; }
  .breadcrumb { margin-bottom: 14px; }
  .page-title { font-size: 18px; }
  .page-desc { margin-bottom: 16px; font-size: 13px; }
  .models-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
}
</style>
