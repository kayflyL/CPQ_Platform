<script setup lang="ts">
/** /lead 独立提交页 —— 同一张线索登记表的完整形态（配置区可填可留空，KP 折叠选填）。
 *  容器 = 商机详情页「线索登记」节点卡同款（requirement-workbench 单层卡头）。
 *  双主题适配：页底/hero 文字随 data-theme 切换；hero-dark（顶栏浅色字）仅暗色主题声明。 */
import { onBeforeUnmount, watchEffect } from 'vue'
import LeadSubmitForm from '@/components/public/LeadSubmitForm.vue'
import { FileTextOutlined } from '@ant-design/icons-vue'
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
</script>

<template>
  <div class="lead-form-page">
    <div class="lfp-inner">
      <div class="lfp-hero">
        <h1>登记你的服务器需求</h1>
        <p>无需注册登录 —— 填一份需求登记表，方案团队 1 个工作日内与您联系</p>
      </div>
      <div class="lfp-card">
        <div class="rw-head">
          <div class="rw-head-title">
            <span class="rich-icon-badge"><FileTextOutlined /></span>
            <div>
              <h3>需求登记</h3>
            </div>
          </div>
        </div>
        <div class="lfp-card-body">
          <LeadSubmitForm source="catalog_general" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 暗色：海军蓝深空底（同 /catalog 银河链路）；浅色：主题渐变底，文字走主题 token */
.lead-form-page {
  min-height: 100vh;
  padding: calc(var(--cpq-header-clearance, 0px) + 8px) 0 60px;
  background: linear-gradient(to bottom, #02050f 0%, #071226 45%, #030814 100%);
  color: #eef3fa;
}
:root[data-theme='light'] .lead-form-page {
  background: var(--cpq-bg-gradient);
  color: var(--cpq-text-primary);
}
.lfp-inner { max-width: 880px; margin: 0 auto; padding: 0 24px; }
.lfp-hero { text-align: center; padding: 44px 0 8px; }
.lfp-hero h1 { font-size: 26px; font-weight: 700; color: #f7fbff; }
.lfp-hero p { font-size: 14px; color: rgba(238, 243, 250, 0.72); margin-top: 10px; }
:root[data-theme='light'] .lfp-hero h1 { color: var(--cpq-text-primary); }
:root[data-theme='light'] .lfp-hero p { color: var(--cpq-text-secondary); }
/* 商机详情页「线索登记」节点卡同款容器（单层卡头：图标徽章 + 标题） */
.lfp-card {
  margin-top: 26px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
.rw-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.rw-head-title { display: flex; align-items: center; gap: 12px; min-width: 0; }
.rw-head h3 { margin: 0; color: var(--cpq-text-primary); font-size: var(--cpq-font-size-base); }
.rich-icon-badge {
  flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--cpq-text-secondary); font-size: 18px;
}
.lfp-card-body { padding: 18px 22px 22px; }
@media (max-width: 640px) {
  .lfp-inner { padding: 0 12px; }
  .lfp-card-body { padding: 14px 14px 16px; }
  .lfp-hero { padding-top: 32px; }
  .lfp-hero h1 { font-size: 22px; }
}
</style>
