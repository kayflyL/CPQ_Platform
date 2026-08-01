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
        <a-menu-item key="/parts">
          <template #icon><DollarOutlined /></template>
          <span>配件</span>
        </a-menu-item>
        <a-menu-item key="/strategies">
          <template #icon><ThunderboltOutlined /></template>
          <span>策略中心</span>
        </a-menu-item>
        <a-sub-menu key="settings">
          <template #icon><SettingOutlined /></template>
          <template #title>设置</template>

          <a-menu-item key="/ai-settings">
            <template #icon><RobotOutlined /></template>
            <span>AI 设置</span>
          </a-menu-item>
          <a-menu-item key="/excel-parser">
            <template #icon><ApiOutlined /></template>
            <span>解析规则</span>
          </a-menu-item>
          <a-menu-item key="/export-templates">
            <template #icon><FileExcelOutlined /></template>
            <span>导出模板</span>
          </a-menu-item>
          <a-menu-item key="/servers/admin">
            <template #icon><DesktopOutlined /></template>
            <span>服务器管理</span>
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

    <!-- 全局浮动「方案助手」入口(右下角,所有页面常驻) -->
    <AssistantFloatingButton v-model:open="assistantOpen" />
    <AssistantPanel v-model:open="assistantOpen" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ProjectOutlined, DollarOutlined, DesktopOutlined, SettingOutlined, FileExcelOutlined, ApiOutlined, ThunderboltOutlined, BulbOutlined, BulbFilled, RobotOutlined } from '@ant-design/icons-vue'
import { useThemeStore } from '@/store/theme'
import AssistantFloatingButton from '@/components/assistant/AssistantFloatingButton.vue'
import AssistantPanel from '@/components/assistant/AssistantPanel.vue'

const router = useRouter()
const route = useRoute()
const themeStore = useThemeStore()
const selectedKeys = ref<string[]>([route.path])
const openKeys = ref<string[]>([])

// 全局方案助手:浮动入口显隐(上下文由 Panel 内 useAssistantContext 按多域 provider 算)
const assistantOpen = ref(false)

// 设置类页面路径（含从「服务器」菜单迁入设置的后台「服务器管理」）
const settingsPaths = ['/ai-settings', '/excel-parser', '/export-templates']

/** 服务器管理面路由：后台页 + 机型/基准编辑页，统一高亮设置子菜单下的「服务器管理」；其余服务器路由高亮顶层「服务器」。 */
const isServersAdminPath = (p: string) =>
  p.startsWith('/servers/admin') ||
  p.startsWith('/servers/base-configs') ||
  p.startsWith('/servers/models/new') ||
  (p.startsWith('/servers/models/') && p.endsWith('/edit'))

watch(() => route.path, (newPath) => {
  // 服务器管理面 → 设置子菜单下的「服务器管理」
  if (isServersAdminPath(newPath)) {
    selectedKeys.value = ['/servers/admin']
    openKeys.value = ['settings']
    return
  }
  // 服务器配置门户及其余服务器路由（机型目录/详情/配置向导）→ 顶层「服务器」
  if (newPath.startsWith('/servers')) {
    selectedKeys.value = ['/servers']
    return
  }
  if (newPath.startsWith('/strategies')) {
    selectedKeys.value = ['/strategies']
    return
  }
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
