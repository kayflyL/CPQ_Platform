<template>
  <div class="app-layout">
    <!-- 顶部：固定导航栏 -->
    <div class="topbar glass-strong">
      <div class="logo-area">
        <div class="logo-text">CPQ</div>
        <div class="logo-sub">Platform</div>
      </div>
      <a-menu 
        v-model:selectedKeys="selectedKeys" 
        v-model:openKeys="openKeys"
        theme="dark" 
        mode="horizontal" 
        @click="handleMenuClick"
        class="top-menu"
      >
        <a-menu-item key="/dashboard">
          <template #icon><DashboardOutlined /></template>
          <span>首页</span>
        </a-menu-item>
        <a-menu-item key="/opportunities">
          <template #icon><ProjectOutlined /></template>
          <span>商机线索</span>
        </a-menu-item>
        <a-menu-item key="/servers">
          <template #icon><DesktopOutlined /></template>
          <span>服务器</span>
        </a-menu-item>
        <a-menu-item key="/base-pricing">
          <template #icon><DollarOutlined /></template>
          <span>配件</span>
        </a-menu-item>
        <a-sub-menu key="settings">
          <template #icon><SettingOutlined /></template>
          <template #title>设置</template>

          <a-menu-item key="/system-settings">
            <template #icon><ControlOutlined /></template>
            <span>系统设置</span>
          </a-menu-item>
          <a-menu-item key="/excel-parser">
            <template #icon><ApiOutlined /></template>
            <span>解析规则</span>
          </a-menu-item>
          <a-menu-item key="/univer-templates">
            <template #icon><FileExcelOutlined /></template>
            <span>导出模板</span>
          </a-menu-item>
        </a-sub-menu>
      </a-menu>
    </div>
    
    <!-- 下方：唯一滚动区域 (内部承载所有页面内容) -->
    <main class="main-scroll">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { DashboardOutlined, ProjectOutlined, DollarOutlined, DesktopOutlined, SettingOutlined, FileExcelOutlined, ApiOutlined, FormOutlined, ControlOutlined } from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const selectedKeys = ref<string[]>([route.path])
const openKeys = ref<string[]>([])

// 设置类页面路径
const settingsPaths = ['/system-settings', '/excel-parser', '/univer-templates']

watch(() => route.path, (newPath) => {
  selectedKeys.value = [newPath]
  // 进入设置类页面时自动展开设置子菜单
  if (settingsPaths.includes(newPath)) {
    openKeys.value = ['settings']
  }
}, { immediate: true })

const handleMenuClick = ({ key }: { key: string }) => {
  router.push(key)
}
</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: var(--cpq-bg-primary);
}

/* 1. 顶部固定栏 */
.topbar {
  height: 56px;
  flex-shrink: 0;
  display: flex;
  flex-direction: row;
  align-items: center;
  z-index: 200;
  padding: 0 16px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}

.topbar :deep(.ant-menu) {
  background: transparent !important;
  color: var(--cpq-text-secondary) !important;
  border-bottom: none !important;
  flex: 1;
}

.topbar :deep(.ant-menu-item:hover) {
  color: var(--cpq-text-primary) !important;
  background: var(--cpq-overlay-w5) !important;
}

.topbar :deep(.ant-menu-item-selected) {
  color: var(--cpq-text-primary) !important;
  background: var(--cpq-accent-primary) !important;
  box-shadow: inset 0 0 12px var(--cpq-overlay-a30);
}
.topbar :deep(.ant-menu-item-selected::after) {
  border-bottom: none !important;
}

.topbar :deep(.anticon) {
  color: var(--cpq-text-secondary) !important;
}
.topbar :deep(.ant-menu-item-selected .anticon) {
  color: var(--cpq-text-primary) !important;
}

.logo-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin-right: 24px;
  flex-shrink: 0;
}

.logo-text {
  font-size: 22px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  letter-spacing: 3px;
  line-height: 1;
  text-shadow: 0 0 20px var(--cpq-overlay-a40);
}

.logo-sub {
  font-size: 9px;
  color: var(--cpq-text-secondary);
  letter-spacing: 1.5px;
  margin-top: 2px;
  text-transform: uppercase;
}

/* 2. 下方滚动区 */
.main-scroll {
  flex: 1;
  height: calc(100vh - 56px);
  overflow-y: auto;
  position: relative;
  background:
    /* 左上 cyan 光晕 */
    radial-gradient(ellipse 60% 40% at 15% 5%, var(--cpq-overlay-a10), transparent),
    /* 右下 blue 光晕 */
    radial-gradient(ellipse 50% 35% at 85% 70%, rgba(80, 80, 255, 0.08), transparent),
    /* 中间 white 微光 */
    radial-gradient(ellipse 40% 30% at 50% 40%, var(--cpq-overlay-w4), transparent),
    var(--cpq-bg-primary);
}

/* 粒子点阵动画 */
.main-scroll::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image:
    radial-gradient(circle 1px at 50px 50px, var(--cpq-overlay-w20) 1px, transparent 1px),
    radial-gradient(circle 1px at 150px 100px, rgba(255,255,255,0.12) 1px, transparent 1px),
    radial-gradient(circle 1px at 250px 50px, var(--cpq-overlay-w15) 1px, transparent 1px),
    radial-gradient(circle 1px at 100px 200px, var(--cpq-overlay-w15) 1px, transparent 1px);
  background-size: 300px 300px;
  animation: particleDrift 60s linear infinite;
}

/* 边缘暗角 (vignette) */
.main-scroll::after {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background: radial-gradient(ellipse at center, transparent 50%, var(--cpq-overlay-b40) 100%);
}

@keyframes particleDrift {
  0% { background-position: 0 0, 50px 50px, 100px 100px, 150px 150px; }
  100% { background-position: 300px 300px, 350px 350px, 400px 400px, 450px 450px; }
}
</style>
