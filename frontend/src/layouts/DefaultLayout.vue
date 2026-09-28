<template>
  <div class="app-layout">
    <!-- 顶栏：通栏页面 chrome（贴顶、满宽、无圆角）——静止全透明，滚动后浮现画布色玻璃底带 -->
    <header
      class="site-header"
      :class="{ 'is-scrolled': scrolled }"
    >
      <div class="site-header-inner">
      <div class="logo-area">
        <div class="logo-text">CPQ</div>
        <div class="logo-sub">Platform</div>
      </div>
      <nav v-if="!isMobile" class="primary-navigation" aria-label="主导航">
        <a
          v-for="item in topItems"
          :key="item.key"
          :href="item.key"
          class="nav-link"
          :class="{ 'is-active': activeKey === item.key }"
          :aria-current="activeKey === item.key ? 'page' : undefined"
          @click.prevent="go(item.key)"
        >{{ item.label }}</a>
        <a-dropdown v-if="showSettings" placement="bottom" :trigger="['click']">
          <a
            class="nav-link"
            :class="{ 'is-active': isSettingsActive }"
            aria-haspopup="menu"
            @click.prevent
          >设置<span class="nav-caret"><DownOutlined /></span></a>
          <template #overlay>
            <div class="cpq-settings-dd">
              <a
                v-for="s in settingsItems"
                :key="s.key"
                :href="s.key"
                class="cpq-settings-dd-link"
                :class="{ 'is-active': activeKey === s.key }"
                @click.prevent="go(s.key)"
              >{{ s.label }}</a>
            </div>
          </template>
        </a-dropdown>
      </nav>
      <div class="topbar-actions">
        <span class="action-pill-wrap">
          <NotificationBell />
        </span>
        <a-dropdown v-if="auth.user" placement="bottomRight">
          <button type="button" class="action-pill user-pill">
            <UserOutlined />
            <span class="user-name">{{ auth.user.name }}</span>
          </button>
          <template #overlay>
            <a-menu @click="onUserMenu">
              <a-menu-item key="logout"><LogoutOutlined /> 退出登录</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
        <button
          type="button"
          class="action-pill icon-pill"
          :title="themeStore.isDark ? '切换浅色主题' : '切换深色主题'"
          @click="themeStore.toggle()"
        >
          <BulbOutlined v-if="themeStore.isDark" />
          <BulbFilled v-else />
        </button>
      </div>
      </div>
    </header>

    <!-- 移动端底部导航：常驻玻璃底栏（3~5 个高频页 + 「更多」），替代原左上角汉堡全屏菜单 -->
    <nav v-if="isMobile" class="mobile-tabbar" aria-label="底部导航">
      <button
        v-for="t in tabItems"
        :key="t.key"
        type="button"
        class="mtab"
        :class="{ 'is-on': activeKey === t.key }"
        @click="go(t.key)"
      >
        <span class="mtab-ic"><component :is="tabIcon(t.key)" /></span>
        <span class="mtab-label">{{ t.label }}</span>
      </button>
      <button
        v-if="moreItems.length"
        type="button"
        class="mtab"
        :class="{ 'is-on': moreOpen || isMoreActive }"
        @click="moreOpen = true"
      >
        <span class="mtab-ic"><EllipsisOutlined /></span>
        <span class="mtab-label">更多</span>
      </button>
    </nav>

    <!-- 移动端「更多」底部面板：收纳第 5+ 项、次级页、设置组与用户卡 -->
    <Transition name="msheet">
      <div v-if="isMobile && moreOpen" class="more-sheet-mask" @click="moreOpen = false">
        <div class="more-sheet" @click.stop>
          <div class="ms-grip" aria-hidden="true"></div>
          <div v-if="moreItems.length" class="ms-sec-label">页面</div>
          <div v-if="moreItems.length" class="ms-grid">
            <button
              v-for="m in moreItems"
              :key="m.key"
              type="button"
              class="ms-item"
              :class="{ 'is-cur': activeKey === m.key }"
              @click="go(m.key)"
            >
              <span class="ms-ic" :style="tileStyle(m.key)">
                <component :is="tabIcon(m.key)" />
                <span v-if="activeKey === m.key" class="ms-cur">当前</span>
              </span>
              <span>{{ m.label }}</span>
            </button>
          </div>
          <div v-if="sheetSecondary.length" class="ms-sec-label ms-sec-label-2nd">商机工具</div>
          <div v-if="sheetSecondary.length" class="ms-grid">
            <button
              v-for="m in sheetSecondary"
              :key="m.key"
              type="button"
              class="ms-item"
              :class="{ 'is-cur': activeKey === m.key }"
              @click="go(m.key)"
            >
              <span class="ms-ic" :style="tileStyle(m.key)">
                <component :is="tabIcon(m.key)" />
                <span v-if="activeKey === m.key" class="ms-cur">当前</span>
              </span>
              <span>{{ m.label }}</span>
            </button>
          </div>
          <div v-if="showSettings" class="ms-sec">
            <div class="ms-sec-label">设置</div>
            <button
              v-for="s in settingsItems"
              :key="s.key"
              type="button"
              class="ms-link"
              :class="{ 'is-active': activeKey === s.key }"
              @click="go(s.key)"
            >
              <span class="ms-link-ic"><component :is="settingsIcon(s.key)" /></span>
              <span>{{ s.label }}</span>
              <span class="ms-link-arr">›</span>
            </button>
          </div>
          <div v-if="auth.user" class="ms-user">
            <span class="ms-avatar">{{ auth.user.name.slice(0, 1) }}</span>
            <span class="ms-user-name">{{ auth.user.name }}</span>
            <button type="button" class="ms-logout" @click="logout"><LogoutOutlined /> 退出登录</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 下方：唯一滚动区域 (内部承载所有页面内容，滚动到顶栏下方触发玻璃化) -->
    <main class="main-scroll" ref="scrollHost" @scroll.passive="onScroll">
      <!-- 顶栏让位用占位元素而非 padding：sticky 偏移从滚动容器 padding 内沿起算，
           padding 会让位与吸顶双重叠加（页面未滚吸顶条就被顶下来压住内容） -->
      <div class="scroll-clearance" aria-hidden="true"></div>
      <router-view v-slot="{ Component, route }">
        <KeepAlive :include="keepAliveNames">
          <component :is="Component" :key="route.path" />
        </KeepAlive>
      </router-view>
      <!-- 底栏让位：与顶部 scroll-clearance 同一让位哲学，页面不再各自写 padding-bottom -->
      <div v-if="isMobile" class="scroll-clearance-bottom" aria-hidden="true"></div>
    </main>

    <!-- 全局浮动「方案助手」入口(右下角,所有页面常驻)；办公室访问策略清零该账号可聊 AI 角色时隐藏 -->
    <template v-if="auth.chatRolesAllowed">
      <AssistantFloatingButton v-model:open="assistantOpen" :model-key="petModel.activePetModel" />
      <AssistantPanel v-model:open="assistantOpen" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { DownOutlined, BulbOutlined, BulbFilled, UserOutlined, LogoutOutlined, HomeOutlined, RobotOutlined, ContainerOutlined, CloudServerOutlined, AppstoreOutlined, SolutionOutlined, EllipsisOutlined, TeamOutlined, ProfileOutlined, FileTextOutlined, RestOutlined } from '@ant-design/icons-vue'
import { useRouter, useRoute } from 'vue-router'
import { useThemeStore } from '@/store/theme'
import { useAuthStore } from '@/store/auth'
import AssistantFloatingButton from '@/components/assistant/AssistantFloatingButton.vue'
import AssistantPanel from '@/components/assistant/AssistantPanel.vue'
import NotificationBell from '@/components/notifications/NotificationBell.vue'
import { usePetModelStore } from '@/store/petModel'
import { useAssistantShell } from '@/composables/useAssistantShell'

// KeepAlive 缓存名单：顶级菜单页，避免切换时反复卸载/重挂载、重新初始化场景与拉数据
const keepAliveNames = [
  'AiOfficeView',
  'OpportunityList',
  'ServerConfig',
  'Parts',
  'StrategyPortal',
]

const router = useRouter()
const route = useRoute()
const themeStore = useThemeStore()
const auth = useAuthStore()
const petModel = usePetModelStore()

// ── 导航数据（RBAC 门控） ──
type NavItem = { key: string; label: string; perm?: string }

const topItems = computed<NavItem[]>(() => {
  const items: NavItem[] = [
    { key: '/galaxy', label: '首页' },
    { key: '/portal', label: '工作台' },
    { key: '/ai-office', label: 'AI 办公室', perm: 'page.office' },
    { key: '/opportunities', label: '商机线索', perm: 'page.opportunities_all' },
    { key: '/servers', label: '服务器', perm: 'page.servers' },
    { key: '/parts', label: '配件', perm: 'page.parts' },
    { key: '/strategies', label: '解决方案', perm: 'page.strategies' },
  ]
  return items.filter((i) => !i.perm || auth.can(i.perm))
})

const settingsItems = computed<NavItem[]>(() => {
  const items: NavItem[] = [
    { key: '/settings/users', label: '用户与权限', perm: 'page.settings.users' },
    { key: '/excel-parser', label: '解析规则', perm: 'page.settings.excel' },
    { key: '/export-templates', label: '导出模板', perm: 'page.settings.templates' },
    { key: '/servers/admin', label: '服务器管理', perm: 'page.settings.admin' },
  ]
  return items.filter((i) => !i.perm || auth.can(i.perm))
})

const showSettings = computed(() => settingsItems.value.length > 0)

/** 服务器管理面路由：后台页 + 机型/基准编辑页，统一高亮设置组下的「服务器管理」；其余服务器路由高亮顶层「服务器」。 */
const isServersAdminPath = (p: string) =>
  p.startsWith('/servers/admin') ||
  p.startsWith('/servers/base-configs') ||
  p.startsWith('/servers/models/new') ||
  (p.startsWith('/servers/models/') && p.endsWith('/edit'))

/** 当前高亮键：路由前缀映射到导航项（详情/子页也能保持父项高亮）。 */
const activeKey = computed(() => {
  const p = route.path
  if (isServersAdminPath(p)) return '/servers/admin'
  const s = settingsItems.value.find((i) => p === i.key || p.startsWith(i.key + '/'))
  if (s) return s.key
  const t = topItems.value.find((i) => p === i.key || p.startsWith(i.key + '/'))
  return t?.key ?? p
})

const isSettingsActive = computed(() =>
  settingsItems.value.some((i) => i.key === activeKey.value)
)

function go(key: string) {
  router.push(key)
  moreOpen.value = false
}

function onUserMenu({ key }: { key: string }) {
  if (key === 'logout') logout()
}

function logout() {
  moreOpen.value = false
  auth.logout()
  router.push('/login')
}

// ── 顶栏底带：滚离页面顶部后浮现（小阈值防抖动；路由切换后复核一次） ──
const scrolled = ref(false)
const scrollHost = ref<HTMLElement | null>(null)
function onScroll() {
  scrolled.value = (scrollHost.value?.scrollTop ?? 0) > 8
}
watch(() => route.path, onScroll)

// ── 移动端（matchMedia 驱动，≤768 底部导航接管；顶栏导航仅桌面） ──
const isMobile = ref(false)

// ── 底部导航：3~5 个高频页 + 「更多」（RBAC 过滤后取 topItems 前 4；首页=星河页 iframe 路由，不进底 tab） ──
const moreOpen = ref(false)
const notGalaxy = (i: NavItem) => i.key !== '/galaxy'
const tabItems = computed(() => topItems.value.filter(notGalaxy).slice(0, 4))
const moreItems = computed(() => topItems.value.filter(notGalaxy).slice(4))
// 次级页（商机域的 AI 线索 / 回收站）收进「更多」面板
const sheetSecondary = computed(() =>
  [
    { key: '/ai-leads', label: 'AI 线索', perm: 'page.opportunities' },
    { key: '/recycle-bin', label: '回收站', perm: 'page.opportunities' },
  ].filter((i) => auth.can(i.perm))
)
const isMoreActive = computed(() =>
  moreItems.value.some((i) => i.key === activeKey.value) ||
  sheetSecondary.value.some((i) => i.key === activeKey.value) ||
  isSettingsActive.value
)

const tabIconMap: Record<string, any> = {
  '/portal': HomeOutlined,
  '/ai-office': RobotOutlined,
  '/opportunities': ContainerOutlined,
  '/servers': CloudServerOutlined,
  '/parts': AppstoreOutlined,
  '/strategies': SolutionOutlined,
  '/ai-leads': RobotOutlined,
  '/recycle-bin': RestOutlined,
}
function tabIcon(key: string) { return tabIconMap[key] ?? AppstoreOutlined }

const settingsIconMap: Record<string, any> = {
  '/settings/users': TeamOutlined,
  '/excel-parser': ProfileOutlined,
  '/export-templates': FileTextOutlined,
  '/servers/admin': CloudServerOutlined,
}
function settingsIcon(key: string) { return settingsIconMap[key] ?? AppstoreOutlined }

// 「更多」面板磁贴：每页专属语义色（马卡龙轮换），告别同蓝
const MS_TILE_COLORS: Record<string, string> = {
  '/parts': 'linear-gradient(140deg, #2fc3a4, #159c80)',
  '/strategies': 'linear-gradient(140deg, #8b93ff, #6a6fe0)',
  '/ai-leads': 'linear-gradient(140deg, #f6b73f, #e0962a)',
  '/recycle-bin': 'linear-gradient(140deg, #f4756f, #d94f57)',
}
function tileStyle(key: string) {
  return { background: MS_TILE_COLORS[key] || 'linear-gradient(140deg, #3b78ff, #2450c8)' }
}
function syncMobile() { isMobile.value = window.matchMedia('(max-width: 768px)').matches }
let _mqListener: ((e: MediaQueryListEvent) => void) | null = null

// 全局方案助手:浮动入口显隐(上下文由 Panel 内 useAssistantContext 按多域 provider 算)。
// 状态住 useAssistantShell 模块单例——工作台 AI 磁贴等任意入口共享同一开关。
const assistantOpen = useAssistantShell().open

onMounted(() => {
  syncMobile()
  const mq = window.matchMedia('(max-width: 768px)')
  _mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', _mqListener)
})
onBeforeUnmount(() => {
  if (_mqListener) window.matchMedia('(max-width: 768px)').removeEventListener('change', _mqListener)
})
</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  /* 手机浏览器地址栏收展会改变可见视口：100vh 是固定最大值，真机上底部内容会被压进地址栏后面
     （头像行「时好时坏」的根因）。100dvh 随地址栏动态伸缩（iOS 15.4+/Chrome 108+），老浏览器回落 100vh */
  height: 100vh;
  height: 100dvh;
  width: 100vw;
  overflow: hidden;
  background: var(--cpq-bg-primary);
}

/* ============================================================
   1. 顶栏 —— 通栏页面 chrome：贴顶满宽、无圆角、静止全透明
      （文字直接躺在共享画布上，如 server-configurator）；
      滚动后浮现「画布色玻璃底带」：glass-3 + blur + 底部 hairline，
      无投影无圆角 —— 是页面的一层表面，不是悬浮对象。
   ============================================================ */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 200;
  border-bottom: 1px solid transparent;
  background: transparent;
  transition:
    background-color var(--cpq-dur-3) var(--cpq-ease-smooth),
    border-color var(--cpq-dur-3) var(--cpq-ease-smooth);
}

.site-header.is-scrolled:not(.is-menu-open) {
  background: var(--cpq-glass-3-bg);
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  border-bottom-color: var(--cpq-border-secondary);
}

/* 内容行：限宽居中与旧胶囊几何对齐（导航位置不跳） */
.site-header-inner {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: min(calc(100vw - 40px), 1680px);
  min-height: 56px;
  margin: 0 auto;
  padding: 6px 8px 6px 18px;
}

/* 首屏深色场景页（如服务器页银河 hero 垫在透明顶栏下）：局部换浅色 token 保可读；
   菜单浮层打开恢复；移动端常驻玻璃不受影响（min-width 门控）。 */
@media (min-width: 769px) {
  html[data-hero-dark='1'] .site-header:not(.is-menu-open) {
    --cpq-text-secondary: rgba(255, 255, 255, 0.72);
    --cpq-text-primary: #ffffff;
    --cpq-border-secondary: rgba(255, 255, 255, 0.22);
    --cpq-overlay-w3: rgba(255, 255, 255, 0.08);
    --cpq-overlay-w5: rgba(255, 255, 255, 0.08);
    --cpq-glass-border-strong: rgba(255, 255, 255, 0.45);
  }
  /* 银河页滚动后：深空色底带续接白字（浅色主题 glass-3 是白玻璃，白字压不住）；
     垫底 hero 页可在 html 上设 --hero-band-bg 用自身主题色（如详情页酒红/暗紫天空） */
  html[data-hero-dark='1'] .site-header.is-scrolled:not(.is-menu-open) {
    background: var(--hero-band-bg, rgba(4, 10, 22, 0.78));
  }
}

.logo-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  letter-spacing: 3px;
  line-height: 1;
}

.logo-sub {
  font-size: 9px;
  color: var(--cpq-text-secondary);
  letter-spacing: 1.5px;
  margin-top: 2px;
  text-transform: uppercase;
}

/* ── 绝对居中导航（不随左右两区宽度变化而偏移） ── */
.primary-navigation {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: clamp(14px, 1.6vw, 28px);
}

.nav-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 14px 2px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
  text-decoration: none;   /* antd-vue reset 不含 a{text-decoration:none}，带 href 的锚点会吃到 UA 默认下划线 */
  cursor: pointer;
  transition: color var(--cpq-dur-1) var(--cpq-ease-smooth);
}

.nav-link:hover { color: var(--cpq-text-primary); }

/* 激活指示条：2px 胶囊下划线，scaleX 从中心展开 */
.nav-link::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 6px;
  height: 2px;
  border-radius: 999px;
  background: var(--cpq-accent-primary);
  transform: scaleX(0);
  transform-origin: center;
  transition: transform 0.22s var(--cpq-ease-out-expo);
}

.nav-link.is-active { color: var(--cpq-text-primary); }
.nav-link.is-active::after { transform: scaleX(1); }

.nav-link:focus-visible {
  outline: 2px solid var(--cpq-accent-primary);
  outline-offset: 2px;
  border-radius: 6px;
}

.nav-caret { font-size: 9px; display: inline-flex; opacity: 0.7; }

/* ── 右侧操作区：胶囊按钮 ── */
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.action-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 12px;
  border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-border-secondary);
  background: var(--cpq-overlay-w5);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition:
    color var(--cpq-dur-1) var(--cpq-ease-smooth),
    border-color var(--cpq-dur-1) var(--cpq-ease-smooth),
    background var(--cpq-dur-1) var(--cpq-ease-smooth),
    transform var(--cpq-dur-2) var(--cpq-ease-out-expo);
}

.action-pill:hover {
  color: var(--cpq-text-primary);
  border-color: var(--cpq-glass-border-strong);
  background: var(--cpq-overlay-a8);
  transform: translateY(-1px);
}

.action-pill.icon-pill {
  width: 36px;
  padding: 0;
  font-size: 15px;
}

.user-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 通知铃铛包进胶囊容器：复位 antd 按钮形状 */
.action-pill-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  min-width: 36px;
  padding: 0 6px;
  border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-border-secondary);
  background: var(--cpq-overlay-w5);
  transition:
    border-color var(--cpq-dur-1) var(--cpq-ease-smooth),
    background var(--cpq-dur-1) var(--cpq-ease-smooth),
    transform var(--cpq-dur-2) var(--cpq-ease-out-expo);
}

.action-pill-wrap:hover {
  border-color: var(--cpq-glass-border-strong);
  background: var(--cpq-overlay-a8);
  transform: translateY(-1px);
}

.site-header :deep(.action-pill-wrap .ant-btn) {
  height: 30px;
  width: 30px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* ============================================================
   2. 下方滚动区 —— 深空/冷空渐变 + 网格；内容从浮动顶栏下方开始
   ============================================================ */
.main-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  position: relative;
  /* 顶栏让位（通栏顶带 56px + 呼吸）：页面内容起始位 + 页内吸顶元素统一吸到顶带下方（抽屉/弹窗内未定义该变量，自动回退）
     让位由 .scroll-clearance 占位元素提供，sticky 偏移因此按视口绝对值起算；满高页用 calc(100% - var(--cpq-header-clearance)) 取整屏 */
  --cpq-sticky-top: 60px;
  --cpq-header-clearance: 72px;
  background: var(--cpq-bg-gradient);
  background-attachment: fixed;
}

.scroll-clearance {
  height: var(--cpq-header-clearance);
  pointer-events: none;
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

/* ============================================================
   3. 移动端：底部导航栏 + 「更多」底部面板
      （规范：3~5 目标 / 图标+标签常显 / 只放导航 / 常驻可见；
       激活态 = 蓝色 tint 药丸，对齐全站 Glass 语言）
   ============================================================ */
.mobile-tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 180;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  height: var(--cpq-tabbar-h);
  padding: 7px 10px calc(7px + env(safe-area-inset-bottom, 0px));
  background: var(--cpq-glass-3-bg);
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  border-top: 1px solid var(--cpq-glass-border);
  box-shadow: 0 -8px 28px var(--cpq-shadow-color, rgba(15, 23, 42, 0.08));
}

.mtab {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: none;
  background: transparent;
  padding: 0;
  font-size: 10px;
  color: var(--cpq-text-muted);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.mtab-ic {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 27px;
  border-radius: 999px;
  font-size: 17px;
  transition: background-color var(--cpq-dur-1) var(--cpq-ease-smooth), color var(--cpq-dur-1) var(--cpq-ease-smooth);
}

.mtab-label {
  font-weight: 500;
  max-width: 64px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mtab.is-on {
  color: var(--cpq-accent-primary);
  font-weight: 700;
}

.mtab.is-on .mtab-ic {
  background: var(--cpq-overlay-a15);
}

.more-sheet-mask {
  position: fixed;
  inset: 0;
  z-index: 179;
  background: var(--cpq-overlay-a40);
  display: flex;
  align-items: flex-end;
  /* 让出底栏高度：sheet 悬于底栏上方（更多 tab 保持可见高亮），不与之互盖 */
  padding-bottom: var(--cpq-tabbar-h);
}

.more-sheet {
  width: 100%;
  border-radius: 22px 22px 0 0;
  border-top: 1px solid var(--cpq-glass-highlight, var(--cpq-glass-border));
  background: var(--cpq-glass-3-bg);
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  box-shadow: 0 -24px 60px var(--cpq-shadow-color, rgba(15, 23, 42, 0.25));
  padding: 10px 16px calc(16px + env(safe-area-inset-bottom, 0px));
  max-height: calc(100vh - var(--cpq-header-clearance, 64px) - var(--cpq-tabbar-h));
  overflow-y: auto;
}

.ms-grip {
  width: 42px;
  height: 4.5px;
  border-radius: 3px;
  background: var(--cpq-overlay-a20);
  margin: 2px auto 14px;
}

.ms-sec-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--cpq-text-muted);
  margin-bottom: 10px;
}

.ms-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px 8px;
  margin-bottom: 6px;
}

.ms-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 4px 2px;
  border: none;
  background: transparent;
  font-size: 10.5px;
  color: var(--cpq-text-secondary);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.ms-ic {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  color: var(--cpq-accent-on-primary);
  background: linear-gradient(140deg, var(--cpq-accent-primary), var(--cpq-accent-primary));
  opacity: 0.92;
}

/* 当前所在页的磁贴：蓝环 + 「当前」角标 */
.ms-item.is-cur .ms-ic {
  outline: 2px solid var(--cpq-accent-primary);
  outline-offset: 2px;
}

.ms-cur {
  position: absolute;
  top: -7px;
  right: -10px;
  font-size: 8.5px;
  font-weight: 800;
  line-height: 1;
  padding: 2px 5px;
  border-radius: 999px;
  background: var(--cpq-accent-primary);
  color: var(--cpq-accent-on-primary);
  box-shadow: 0 0 0 2px var(--cpq-bg-primary);
}

.ms-item.is-cur span:last-of-type {
  color: var(--cpq-accent-primary);
  font-weight: 700;
}

.ms-sec-label-2nd { margin-top: 12px; }

.ms-sec {
  border-top: 1px solid var(--cpq-overlay-w6);
  margin-top: 12px;
  padding-top: 12px;
}

.ms-link {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 4px;
  border: none;
  border-bottom: 1px dashed var(--cpq-overlay-w6);
  background: transparent;
  font-size: 14px;
  color: var(--cpq-text-primary);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.ms-link:last-child { border-bottom: none; }

.ms-link.is-active { color: var(--cpq-accent-primary); font-weight: 600; }

.ms-link-ic {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  background: var(--cpq-overlay-a8);
  color: var(--cpq-accent-primary);
}

.ms-link-arr { margin-left: auto; color: var(--cpq-text-muted); font-size: 13px; }

.ms-user {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 14px;
  background: var(--cpq-overlay-w5);
}

.ms-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: var(--cpq-accent-on-primary);
  background: var(--cpq-accent-primary);
  flex: none;
}

.ms-user-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ms-logout {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 34px;
  padding: 0 13px;
  flex-shrink: 0;
  border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-overlay-danger15, var(--cpq-overlay-w10));
  background: var(--cpq-overlay-w5);
  color: var(--cpq-accent-danger);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

/* 更多面板：从底部滑入 */
.msheet-enter-active,
.msheet-leave-active {
  transition: opacity var(--cpq-dur-2) var(--cpq-ease-smooth);
}

.msheet-enter-active .more-sheet,
.msheet-leave-active .more-sheet {
  transition: transform 0.32s var(--cpq-ease-out-expo, var(--cpq-ease-smooth));
}

.msheet-enter-from,
.msheet-leave-to {
  opacity: 0;
}

.msheet-enter-from .more-sheet,
.msheet-leave-to .more-sheet {
  transform: translateY(100%);
}

.scroll-clearance-bottom {
  height: var(--cpq-tabbar-inset);
  pointer-events: none;
}

@media (max-width: 1100px) {
  .user-name { display: none; }
  .user-pill { padding: 0; width: 36px; }
}

@media (max-width: 768px) {
  /* 顶带常驻玻璃（移动端页面无 Hero 区，透明态会与内容打架） */
  .site-header {
    background: var(--cpq-glass-3-bg);
    -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
    backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
    border-bottom-color: var(--cpq-border-secondary);
  }

  .site-header-inner {
    width: auto;
    min-height: 52px;
    padding: 4px 12px;
  }

  .logo-text { font-size: 16px; }
  .logo-sub { font-size: 8px; }
  .main-scroll {
    --cpq-sticky-top: 56px;
    --cpq-header-clearance: 64px;
  }
}
</style>

<style>
/* ── 底部导航全局变量：栏高与让位高度（含 iPhone 安全区），全局可引用。
   JS（桌宠避让 useAssistantFab）同步读取 58px 常量，改动需两处同步 ── */
:root {
  --cpq-tabbar-h: 58px;
  --cpq-tabbar-inset: 0px;
}

@media (max-width: 768px) {
  :root {
    --cpq-tabbar-inset: calc(58px + env(safe-area-inset-bottom, 0px));
  }
}

/* 设置下拉面板：挂在 body 层级，scoped 够不到，走全局 */
.cpq-settings-dd {
  min-width: 176px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  background: var(--cpq-glass-3-bg);
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  border: 1px solid var(--cpq-glass-border);
  box-shadow: var(--cpq-shadow-lg), inset 0 1px 0 var(--cpq-glass-highlight);
}

.cpq-settings-dd-link {
  padding: 9px 12px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
  text-decoration: none;
  cursor: pointer;
}

.cpq-settings-dd-link:hover {
  background: var(--cpq-overlay-a8);
  color: var(--cpq-text-primary);
}

.cpq-settings-dd-link.is-active {
  background: var(--cpq-overlay-a15);
  color: var(--cpq-accent-primary);
  font-weight: 600;
}
</style>
