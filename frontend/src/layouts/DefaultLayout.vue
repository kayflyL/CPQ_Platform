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
        :theme="themeStore.isDark ? 'dark' : 'light'"
        mode="horizontal"
        @click="handleMenuClick"
        class="top-menu"
      >
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
      <div class="topbar-actions">
        <a-button type="text" class="theme-toggle" @click="themeStore.toggle()">
          <BulbOutlined v-if="themeStore.isDark" />
          <BulbFilled v-else />
        </a-button>
      </div>
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
import { ProjectOutlined, DollarOutlined, DesktopOutlined, SettingOutlined, FileExcelOutlined, ApiOutlined, FormOutlined, ControlOutlined, BulbOutlined, BulbFilled } from '@ant-design/icons-vue'
import { useThemeStore } from '@/store/theme'

const router = useRouter()
const route = useRoute()
const themeStore = useThemeStore()
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

/* 顶栏右侧操作区 */
.topbar-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  margin-left: 8px;
}

.theme-toggle {
  color: var(--cpq-text-secondary) !important;
  font-size: 16px;
}
.theme-toggle:hover {
  color: var(--cpq-accent-primary) !important;
}

/* 2. 下方滚动区 —— 深空/冷空渐变 + 网格 */
.main-scroll {
  flex: 1;
  height: calc(100vh - 56px);
  overflow-y: auto;
  position: relative;
  background: var(--cpq-bg-gradient);
  background-attachment: fixed;
}

/* 内容置于网格层之上，路由切换时淡入 */
.main-scroll > * {
  position: relative;
  z-index: 1;
  animation: cpq-fade var(--cpq-dur-3) var(--cpq-ease-smooth);
}

/* 网格层 —— 数据中心技术感，中间显、边缘淡 */
.main-scroll::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image:
    linear-gradient(var(--cpq-grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--cpq-grid-line) 1px, transparent 1px);
  background-size: 48px 48px;
  -webkit-mask-image: radial-gradient(ellipse 75% 60% at 50% 35%, black 35%, transparent 100%);
  mask-image: radial-gradient(ellipse 75% 60% at 50% 35%, black 35%, transparent 100%);
}

/* 浅色：logo 去发光（背景渐变两套已自动跟随主题） */
[data-theme='light'] .logo-text {
  text-shadow: none;
}
</style>
