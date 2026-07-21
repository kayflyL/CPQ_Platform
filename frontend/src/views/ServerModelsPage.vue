<script setup lang="ts">
/** 机型目录页（/servers/types/:typeId）— 展示某类型下所有机型，点击进入配置向导 */
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerType, type ServerModel } from '@/api/serverConfig'
import ModelShowcase from '@/components/server-config/ModelShowcase.vue'
import { matchShowcase } from '@/components/server-config/showcase-config'

const route = useRoute()
const router = useRouter()

const typeId = computed(() => Number(route.params.typeId))
const currentType = ref<ServerType | null>(null)
const models = ref<ServerModel[]>([])
const loading = ref(false)
const showcaseConfig = computed(() => matchShowcase(currentType.value?.name || ''))

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

function goToConfig(model: ServerModel) {
  router.push(`/servers/config/${model.id}`)
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
      <ModelShowcase v-if="showcaseConfig" :type-name="currentType?.name || ''" />

      <!-- 机型卡片网格 -->
      <div class="models-grid" v-if="models.length">
        <div v-for="m in models" :key="m.id" class="model-card" @click="goToConfig(m)">
          <div class="m-top">
            <span class="mn">{{ m.name }}</span>
            <span class="m-tag">{{ m.form || '—' }}</span>
          </div>
          <div class="mu">{{ m.use || '通用场景' }}</div>
          <div class="m-specs">
            <div><span class="k">盘位</span><span class="v">{{ m.bays || '—' }}</span></div>
          </div>
          <button class="m-pick">配置这台 →</button>
        </div>
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
.model-card {
  padding: 24px;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 18px;
  cursor: pointer;
  transition: all .3s cubic-bezier(.16,1,.3,1);
  background: linear-gradient(135deg,
    var(--cpq-overlay-w6) 0%,
    var(--cpq-overlay-w3) 40%,
    var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px);
  box-shadow:
    0 22px 64px var(--cpq-overlay-b30),
    0 0 34px var(--cpq-overlay-a4),
    inset 0 1px 0 var(--cpq-overlay-w15),
    inset 0 -18px 48px var(--cpq-overlay-b15);
}
.model-card:hover {
  border-color: var(--cpq-overlay-a30);
  transform: translateY(-2px);
  box-shadow:
    0 22px 64px var(--cpq-shadow-color-strong),
    0 0 34px var(--cpq-overlay-a15),
    inset 0 1px 0 var(--cpq-overlay-w15),
    inset 0 -18px 48px var(--cpq-shadow-color-soft);
}
.m-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.mn {
  font-size: 17px;
  font-weight: 600;
  color: var(--cpq-text-primary, #E8ECEF);
}
.m-tag {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 4px;
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-secondary,#9BA1AA);
  border: 1px solid var(--cpq-overlay-w10);
}
.mu {
  color: var(--cpq-text-secondary,#9BA1AA);
  font-size: 14px;
  min-height: 42px;
  margin-bottom: 16px;
  line-height: 1.5;
}
.m-specs {
  display: flex;
  gap: 20px;
  padding-top: 14px;
  border-top: 1px solid var(--cpq-overlay-w10);
  margin-bottom: 16px;
}
.m-specs .k {
  font-size: 12px;
  color: var(--cpq-text-muted,#6E7582);
  display: block;
  margin-bottom: 3px;
}
.m-specs .v {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary, #E8ECEF);
}
.m-pick {
  width: 100%;
  padding: 10px;
  border-radius: 8px;
  background: transparent;
  border: 1px solid var(--cpq-overlay-w20);
  color: var(--cpq-text-secondary,#9BA1AA);
  font-size: 13px;
  transition: all .2s;
  cursor: pointer;
}
.model-card:hover .m-pick {
  background: var(--cpq-overlay-a15);
  border-color: var(--cpq-accent-primary,#1677FF);
  color: var(--cpq-accent-primary,#1677FF);
}
.sc-empty {
  color: var(--cpq-text-muted,#6E7582);
  text-align: center;
  padding: 60px 0;
  font-size: 14px;
}
</style>
