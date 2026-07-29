<script setup lang="ts">
/** 机型目录页（/servers/types/:typeId）— 展示某类型下所有机型，点击进入配置向导 */
import { ref, onMounted, computed } from 'vue'
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

    const modelsRes = await catalogApi.listModels(typeId.value)
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

onMounted(loadTypeAndModels)
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
          @click="goToDetail(m)"
        />
      </div>
      <div v-else-if="!loading" class="sc-empty">该类型下暂无机型，去「管理」添加。</div>
    </div>
  </div>
</template>

<style scoped>
.models-page {
  padding: 4px 0 80px;
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
  color: var(--cpq-text-secondary, #9BA1AA);
  font-size: 14px;
  padding: 4px 8px;
}
.back-btn:hover {
  color: var(--cpq-accent-primary, #1677FF);
}
.current-type {
  color: var(--cpq-text-primary, #E8ECEF);
  font-size: 14px;
  font-weight: 500;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--cpq-text-primary, #E8ECEF);
}
.page-desc {
  color: var(--cpq-text-secondary, #9BA1AA);
  font-size: 14px;
  margin-bottom: 28px;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
}
.sc-empty {
  color: var(--cpq-text-muted,#6E7582);
  text-align: center;
  padding: 60px 0;
  font-size: 14px;
}
</style>
