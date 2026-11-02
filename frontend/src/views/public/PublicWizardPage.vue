<script setup lang="ts">
/**
 * 公开版配置向导页（/catalog/config/:modelId）—— ConfigWizard 组件的公开宿主。
 * 复用同一向导组件（价格 fail-closed：匿名拿到的 KP/配件数据自动剥价，组件价格列本就 price-visible=false），
 * 页面级差异：无管理入口；完成动作=向导 leadMode「提交配置」→ ConfigSubmitPanel overlay
 * （机型/平台/机箱/电源/部件清单自动带出，用户只补数量/维保/联系方式）。
 */
import { ref, computed, onMounted, watchEffect, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerModel } from '@/api/serverConfig'
import ConfigWizard from '@/components/server-config/ConfigWizard.vue'
import ConfigSubmitPanel from '@/components/public/ConfigSubmitPanel.vue'
import { useThemeStore } from '@/store/theme'

const themeStore = useThemeStore()

// 固定暗色页垫在透明顶栏下：顶栏文字恒浅色（同内部 /servers 机制）。
// 浅色主题页顶是浅底，白字顶栏不可读，故只随暗色主题声明。
function markHeroDark(on: boolean) {
  if (on) document.documentElement.dataset.heroDark = '1'
  else delete document.documentElement.dataset.heroDark
}
// watchEffect 立即执行一次：挂载即按当前主题声明；主题中途切换同步跟随
const stopHero = watchEffect(() => markHeroDark(themeStore.isDark))
onBeforeUnmount(() => { stopHero(); markHeroDark(false) })

const route = useRoute()
const router = useRouter()
const modelId = computed(() => Number(route.params.modelId))
const currentModel = ref<ServerModel | null>(null)
const loading = ref(false)
const wizardRef = ref<InstanceType<typeof ConfigWizard> | null>(null)
const showSubmitPanel = ref(false)
const submitMeta = ref<Record<string, any>>({})
const submitKpRows = ref<Array<Record<string, any>>>([])

async function loadModel() {
  loading.value = true
  try {
    currentModel.value = await catalogApi.getModel(modelId.value)
  } catch (e: any) {
    console.error('加载机型失败', e)
  } finally { loading.value = false }
}

function goBack() {
  if (window.history.state?.back) { router.back(); return }
  if (currentModel.value?.server_type_id) router.push(`/catalog/types/${currentModel.value.server_type_id}`)
  else router.push('/catalog')
}

/** 向导「提交配置」→ 弹确认面板：机型元数据 + KP 行自动带出（无价格） */
function openSubmitPanel() {
  const m = currentModel.value
  if (!m) return
  const snap = wizardRef.value?.getPublicSnapshot?.() || { kp_rows: [] as Array<Record<string, any>>, meta: {} as Record<string, any> }
  submitMeta.value = {
    ...(snap.meta || {}),
    server_model: snap.meta?.server_model || m.name || '',
    platform_type: snap.meta?.platform_type || m.base_config?.series || '',
    chassis_form: snap.meta?.chassis_form || m.base_config?.form || '',
    chassis_bays: snap.meta?.chassis_bays || m.base_config?.bays || 0,
  }
  submitKpRows.value = snap.kp_rows || []
  showSubmitPanel.value = true
}

function onViewSpec() {
  wizardRef.value?.openSpecSheet?.()
}

onMounted(loadModel)
</script>

<template>
  <div class="pub-wizard">
    <div class="pw-topbar">
      <button class="pw-back" type="button" @click="goBack">← 返回</button>
      <span class="pw-crumb">配置服务器<span v-if="currentModel"> · {{ currentModel.name }}</span></span>
    </div>

    <a-spin :spinning="loading">
      <ConfigWizard v-if="currentModel" ref="wizardRef" :model="currentModel" lead-mode @submit-config="openSubmitPanel" />
    </a-spin>

    <!-- 提交配置 overlay：配置确认（自动带出）+ 数量/维保 + 查看规格书 + 联系信息 -->
    <ConfigSubmitPanel
      v-if="showSubmitPanel"
      :meta="submitMeta"
      :kp-rows="submitKpRows"
      @close="showSubmitPanel = false"
      @view-spec="onViewSpec"
    />
  </div>
</template>

<style scoped>
/* 暗色：海军蓝深空底（同 /catalog 银河链路）；浅色：主题渐变底，文字走主题 token */
.pub-wizard {
  min-height: calc(100vh - 52px);
  background: linear-gradient(to bottom, #02050f 0%, #071226 45%, #030814 100%);
  color: #eef3fa;
  padding: 0 0 80px;
}
:root[data-theme='light'] .pub-wizard {
  background: var(--cpq-bg-gradient);
  color: var(--cpq-text-primary);
}
.pw-topbar {
  display: flex; align-items: center; gap: 14px;
  /* 顶栏让位由布局层 .scroll-clearance 提供，这里不再重复让位（曾双重让位出 156px 空白带） */
  padding: 12px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: var(--cpq-overlay-b85);
}
:root[data-theme='light'] .pw-topbar {
  border-bottom: 1px solid var(--cpq-border-secondary);
  background: transparent;
}
.pw-back {
  background: none; border: none; cursor: pointer; font-family: inherit;
  color: rgba(238, 243, 250, 0.72); font-size: 14px; padding: 4px 8px;
}
.pw-back:hover { color: #fff; }
:root[data-theme='light'] .pw-back { color: var(--cpq-text-secondary); }
:root[data-theme='light'] .pw-back:hover { color: var(--cpq-accent-primary); }
.pw-crumb { font-size: 15px; font-weight: 600; color: #f2f8ff; }
:root[data-theme='light'] .pw-crumb { color: var(--cpq-text-primary); }
</style>
