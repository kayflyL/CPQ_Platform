<script setup lang="ts">
/**
 * 公开版配置向导页（/catalog/config/:modelId）—— ConfigWizard 组件的公开宿主。
 * 复用同一向导组件（价格 fail-closed：匿名拿到的 KP/配件数据自动剥价，组件价格列本就 price-visible=false），
 * 页面级差异：无管理入口；完成动作=「提交需求，获取报价」展开公开线索登记表（选型快照预填）。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerModel } from '@/api/serverConfig'
import ConfigWizard from '@/components/server-config/ConfigWizard.vue'
import LeadSubmitForm from '@/components/public/LeadSubmitForm.vue'
import { FileTextOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

// 固定暗色页垫在透明顶栏下：顶栏文字恒浅色（同内部 /servers 机制）
function markHeroDark(on: boolean) {
  if (on) document.documentElement.dataset.heroDark = '1'
  else delete document.documentElement.dataset.heroDark
}

const route = useRoute()
const router = useRouter()

const modelId = computed(() => Number(route.params.modelId))
const currentModel = ref<ServerModel | null>(null)
const loading = ref(false)
const wizardRef = ref<InstanceType<typeof ConfigWizard> | null>(null)
const showLeadForm = ref(false)
const initialSlots = ref<Record<string, any> | null>(null)

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

/** 完成配置 → 展开登记表：机型/配置意向 + 向导选型快照（KP 行）预填 */
function openLeadForm() {
  const m = currentModel.value
  if (!m) return
  const snap = wizardRef.value?.getPublicSnapshot?.() || { kp_rows: [] }
  initialSlots.value = {
    configs: [{
      name: 'CFG1',
      server_model: m.name || '',
      platform_type: m.base_config?.series || '',
      chassis_form: m.base_config?.form || '',
      qty: 1,
      warranty_years: '3',
      kp_rows: snap.kp_rows || [],
    }],
    config_relation: 'compose',
  }
  showLeadForm.value = true
  message.success('已按当前配置预填需求，请补全联系方式提交')
  setTimeout(() => document.getElementById('public-lead-anchor')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
}

onMounted(() => {
  markHeroDark(true)
  loadModel()
})
onBeforeUnmount(() => markHeroDark(false))
</script>

<template>
  <div class="pub-wizard">
    <div class="pw-topbar">
      <button class="pw-back" type="button" @click="goBack">← 返回</button>
      <span class="pw-crumb">配置服务器<span v-if="currentModel"> · {{ currentModel.name }}</span></span>
    </div>

    <a-spin :spinning="loading">
      <ConfigWizard v-if="currentModel" ref="wizardRef" :model="currentModel" />
    </a-spin>

    <!-- 公开完成动作：从选型直达线索登记 -->
    <div class="pw-lead-cta">
      <div>
        <b>配置好了？</b>
        <span>按你配置的这台实配报价，无任何约束 —— 1 个工作日内回复</span>
      </div>
      <button class="pw-cta-btn" type="button" @click="showLeadForm ? showLeadForm = false : openLeadForm()">
        {{ showLeadForm ? '收起登记表' : '提交需求，获取报价 →' }}
      </button>
    </div>

    <div v-if="showLeadForm" id="public-lead-anchor" class="pw-lead-panel">
      <div class="rw-head">
        <div class="rw-head-title">
          <span class="rich-icon-badge"><FileTextOutlined /></span>
          <div>
            <span class="rw-eyebrow">线索登记</span>
            <h3>需求登记</h3>
          </div>
        </div>
      </div>
      <div class="pw-lead-body">
        <LeadSubmitForm source="catalog_model" :initial-slots="initialSlots" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.pub-wizard {
  min-height: calc(100vh - 52px);
  background: linear-gradient(to bottom, #02050f 0%, #071226 45%, #030814 100%);
  color: #eef3fa;
  padding: 0 0 80px;
}
.pw-topbar {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 24px;
  padding-top: calc(var(--cpq-header-clearance, 0px) + 12px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: var(--cpq-overlay-b85);
}
.pw-back {
  background: none; border: none; cursor: pointer; font-family: inherit;
  color: rgba(238, 243, 250, 0.72); font-size: 14px; padding: 4px 8px;
}
.pw-back:hover { color: #fff; }
.pw-crumb { font-size: 15px; font-weight: 600; color: #f2f8ff; }
.pw-lead-cta {
  max-width: 1080px; margin: 26px auto 0; padding: 20px 28px;
  display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap;
  border: 1px solid rgba(255, 255, 255, 0.2); border-radius: var(--cpq-radius-lg);
  background: linear-gradient(135deg, var(--cpq-overlay-a10), var(--cpq-overlay-a4));
}
.pw-lead-cta b { font-size: var(--cpq-font-size-lg); color: #f2f8ff; display: block; }
.pw-lead-cta span { font-size: 13px; color: rgba(238, 243, 250, 0.72); }
.pw-cta-btn {
  padding: 11px 26px; font-size: 14.5px; font-weight: 600; cursor: pointer; flex-shrink: 0;
  background: var(--cpq-accent-primary); color: #fff; border: none; border-radius: var(--cpq-radius-md);
}
.pw-cta-btn:hover { background: var(--cpq-accent-primary-light); }
.pw-lead-panel {
  max-width: 1080px; margin: 20px auto 0;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
.pw-lead-panel .rw-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.pw-lead-panel .rw-head-title { display: flex; align-items: center; gap: 12px; min-width: 0; }
.pw-lead-panel .rw-eyebrow { display: none; }
.pw-lead-panel .rw-head h3 { margin: 0; color: var(--cpq-text-primary); font-size: 14px; }
.pw-lead-panel .rich-icon-badge {
  width: 40px; height: 40px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: var(--cpq-radius-md);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.92), rgba(139, 92, 246, 0.88));
  color: #fff; font-size: 18px;
  box-shadow: 0 6px 18px rgba(99, 102, 241, 0.28);
}
.pw-lead-body { padding: 18px 22px 22px; }
</style>
