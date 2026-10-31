<template>
  <div class="os-page">
    <OfficeTopBar />

    <div class="os-body">
      <button class="os-crumb" @click="router.push('/')">← 返回桌面</button>

      <div class="os-hero">
        <div class="os-icon">C</div>
        <div class="os-hero-main">
          <div class="os-title">CPQ 系统</div>
          <div class="os-desc">商机 · 报价 · 交付全流程 · 接入于 2026-10</div>
        </div>
        <button class="os-open" @click="openSystem">打开系统 ↗</button>
      </div>

      <div class="os-cards">
        <div class="os-card">
          <ColleagueAccessPanel :colleagues="colleagues" />
        </div>

        <div class="os-card">
          <div class="os-card-head">
            <div class="os-card-title">系统信息</div>
            <div class="os-card-desc">该应用在办公室的接入档案（只读；接入信息由接入向导维护）。</div>
          </div>
          <div class="os-row"><span class="os-label">系统地址</span><span class="os-unit os-num">http://localhost:5173</span></div>
          <div class="os-row"><span class="os-label">接入方式</span><span class="os-unit">独立门面 · 新标签打开</span></div>
          <div class="os-row"><span class="os-label">接入时间</span><span class="os-unit os-num">2026-10</span></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/* CPQ 系统设置页（/office/app/cpq/settings）：
   卡一 = AI 角色访问权限（ColleagueAccessPanel 原样迁入，真相源搬家不复制）；
   卡二 = 系统信息接入档案（只读）。 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import OfficeTopBar from './OfficeTopBar.vue'
import ColleagueAccessPanel from './ColleagueAccessPanel.vue'
import { officeApi } from '@/api/office'

const router = useRouter()
const colleagues = ref<any[]>([])

function openSystem() { window.open('/', '_blank') }

onMounted(async () => {
  try {
    const cfg = await officeApi.teamConfig()
    colleagues.value = Array.isArray(cfg.colleagues) ? cfg.colleagues : []
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
</style>
