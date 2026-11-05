<template>
  <div class="os-page">
    <OfficeTopBar />

    <div class="os-body">
      <button class="os-crumb" @click="router.push('/')">← 返回桌面</button>

      <div class="os-hero">
        <div class="os-icon">C</div>
        <div class="os-hero-main">
          <div class="os-title">{{ appName }}</div>
          <div class="os-desc">{{ appDesc || '商机 · 报价 · 交付全流程' }} · 接入于 2026-10</div>
        </div>
        <button class="os-open" @click="openSystem">打开系统 ↗</button>
      </div>

      <div class="os-cards">
        <div class="os-card">
          <div class="os-card-head">
            <div class="os-card-title">系统信息</div>
            <div class="os-card-desc">展示于桌面磁贴；修改后保存即可生效。</div>
          </div>
          <div class="os-row"><span class="os-label">系统名称</span><a-input v-model:value="appName" class="os-input" :maxlength="24" placeholder="CPQ 系统" /></div>
          <div class="os-row os-row--top"><span class="os-label">描述</span><a-input v-model:value="appDesc" class="os-input" :maxlength="80" placeholder="一句话介绍这个系统" /></div>
          <div class="os-row"><span class="os-label">系统地址</span><span class="os-unit os-num">http://localhost:5173</span></div>
          <div class="os-row"><span class="os-label">接入方式</span><span class="os-unit">独立门面 · 新标签打开</span></div>
          <div class="os-row"><span class="os-label">接入时间</span><span class="os-unit os-num">2026-10</span></div>
          <div class="os-actions"><button class="os-save" :disabled="savingMeta" @click="saveAppMeta">{{ savingMeta ? '保存中…' : '保存' }}</button></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/* CPQ 系统设置页（/office/app/cpq/settings）：
   只管 CPQ 侧的系统信息（名称/描述写回办公室档案 offices 配置，桌面磁贴读它）；
   AI 办公室内部权限（访问权限/团队隔离/价格可见性/管理面进入门槛）归
   AI 办公室管理面「运行与权限 → 账户与权限」（AiOfficeManagement），此处不放。 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import OfficeTopBar from './OfficeTopBar.vue'
import { officeApi, type OfficeProfile } from '@/api/office'

const router = useRouter()
const offices = ref<OfficeProfile[]>([])
const appName = ref('CPQ 系统')
const appDesc = ref('')
const savingMeta = ref(false)

function openSystem() { window.open('/', '_blank') }

async function saveAppMeta() {
  savingMeta.value = true
  try {
    const next = offices.value.map((o) => o.key === 'cpq'
      ? { ...o, name: appName.value.trim() || 'CPQ 系统', description: appDesc.value.trim() }
      : o)
    const res = await officeApi.updateOffices({ offices: next })
    offices.value = Array.isArray(res.offices) ? res.offices : next
    message.success('已保存，桌面磁贴已更新')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingMeta.value = false
  }
}

onMounted(async () => {
  try {
    const cfg = await officeApi.teamConfig()
    offices.value = Array.isArray(cfg.offices) ? cfg.offices : []
    const cpq = offices.value.find((o) => o.key === 'cpq')
    if (cpq) {
      appName.value = cpq.name || 'CPQ 系统'
      appDesc.value = cpq.description || ''
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '办公室数据加载失败，请重新登录后再试')
  }
})
</script>

<style scoped>
.os-page { min-height: 100vh; }
.os-body { max-width: 880px; margin: 0 auto; padding: var(--cpq-space-4) var(--cpq-space-5) 80px; }
.os-crumb {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted);
  padding: var(--cpq-space-1) 0; margin-bottom: var(--cpq-space-3);
  transition: color var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.os-crumb:hover { color: var(--cpq-accent-primary); }
.os-hero { display: flex; align-items: center; gap: var(--cpq-space-4); margin-bottom: var(--cpq-space-5); }
.os-icon {
  width: 52px; height: 52px; flex: none; border-radius: var(--cpq-radius-xl);
  background: var(--cpq-accent-gradient);
  display: grid; place-items: center;
  color: var(--cpq-accent-on-primary); font-size: var(--cpq-font-size-xl); font-weight: 800;
  box-shadow: 0 8px 20px var(--cpq-shadow-color-soft), inset 0 1px 0 var(--cpq-overlay-w15);
}
.os-hero-main { flex: 1; min-width: 0; }
.os-title { font-size: var(--cpq-font-size-2xl); font-weight: 700; color: var(--cpq-text-primary); }
.os-desc { margin-top: 2px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.os-open {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 8px;
  height: 36px; padding: 0 var(--cpq-space-4); border-radius: var(--cpq-radius-sm);
  background: var(--cpq-accent-gradient); color: var(--cpq-accent-on-primary);
  font-size: var(--cpq-font-size-base); font-weight: 600;
  box-shadow: 0 4px 14px var(--cpq-shadow-color-soft), inset 0 1px 0 var(--cpq-overlay-w15);
  transition: transform var(--cpq-dur-1) var(--cpq-ease-spring), box-shadow var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.os-open:hover { transform: translateY(-1px); box-shadow: 0 8px 20px var(--cpq-shadow-color-strong); }
.os-open:active { transform: none; }
.os-cards { display: grid; gap: var(--cpq-space-4); }
.os-card {
  padding: var(--cpq-space-4);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-1-bg);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
}
.os-card-head { margin-bottom: var(--cpq-space-2); }
.os-card-title { font-size: var(--cpq-font-size-lg); font-weight: 700; color: var(--cpq-text-primary); }
.os-card-desc { margin-top: 3px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); line-height: 1.55; }
.os-row {
  display: flex; align-items: center; justify-content: space-between; gap: var(--cpq-space-3);
  padding: var(--cpq-space-3) 0;
  border-bottom: 1px solid var(--cpq-border-secondary);
}
.os-row:last-child { border-bottom: none; }
.os-label { font-size: var(--cpq-font-size-base); color: var(--cpq-text-primary); }
.os-unit { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.os-num { font-variant-numeric: tabular lining; font-feature-settings: 'tnum' 1, 'lnum' 1; }
.os-row--top { align-items: flex-start; }
.os-row--top .os-label { padding-top: 6px; }
.os-input { width: 280px; max-width: 60%; }
.os-actions { display: flex; justify-content: flex-end; padding-top: var(--cpq-space-3); }
.os-save {
  height: 30px; padding: 0 var(--cpq-space-4); border-radius: var(--cpq-radius-sm);
  background: var(--cpq-accent-gradient); color: var(--cpq-accent-on-primary);
  font-size: var(--cpq-font-size-sm); font-weight: 600;
  box-shadow: 0 3px 10px var(--cpq-shadow-color-soft);
  transition: transform var(--cpq-dur-1) var(--cpq-ease-spring);
}
.os-save:hover { transform: translateY(-1px); }
.os-save:disabled { opacity: .6; transform: none; }
</style>
