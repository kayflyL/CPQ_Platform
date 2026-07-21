<script setup lang="ts">
/** 配置向导页（/servers/config/:modelId）— 四步配置流程 */
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerModel } from '@/api/serverConfig'
import ConfigWizard from '@/components/server-config/ConfigWizard.vue'

const route = useRoute()
const router = useRouter()

const modelId = computed(() => Number(route.params.modelId))
const currentModel = ref<ServerModel | null>(null)
const loading = ref(false)

async function loadModel() {
  loading.value = true
  try {
    currentModel.value = await catalogApi.getModel(modelId.value)
  } catch (e: any) {
    console.error('加载机型失败', e)
  } finally { loading.value = false }
}

function goBack() {
  if (currentModel.value?.server_type_id) {
    router.push(`/servers/types/${currentModel.value.server_type_id}`)
  } else {
    router.push('/servers')
  }
}

onMounted(loadModel)
</script>

<template>
  <div class="config-page">
    <div class="page-inner">
      <!-- 面包屑导航 -->
      <div class="breadcrumb">
        <button class="sc-back" @click="goBack">
          ← 返回机型目录
        </button>
        <a-divider type="vertical" />
        <span class="current-model">{{ currentModel?.name || '加载中...' }}</span>
      </div>

      <!-- 配置向导 -->
      <ConfigWizard v-if="currentModel" :model="currentModel" />
      <div v-else-if="!loading" class="sc-empty">机型不存在</div>
    </div>
  </div>
</template>

<style scoped>
.config-page {
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
.current-model {
  color: var(--cpq-text-primary, #E8ECEF);
  font-size: 14px;
  font-weight: 500;
}
.sc-back { padding: 6px 14px; border: 1px solid var(--cpq-border-light,var(--cpq-overlay-w20)); border-radius: 8px; color: var(--cpq-text-secondary,#9BA1AA); background: transparent; cursor: pointer; font-size: 13px; transition: all .2s; }
.sc-back:hover { color: var(--cpq-accent-primary,#1677FF); border-color: var(--cpq-accent-primary,#1677FF); }

.sc-empty {
  color: var(--cpq-text-muted,#6E7582);
  text-align: center;
  padding: 60px 0;
  font-size: 14px;
}
</style>
