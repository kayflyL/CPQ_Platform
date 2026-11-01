import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'ant-design-vue/dist/reset.css'
import './styles/tokens.css'
import './styles/reset.css'
import './styles/glass.css'
import './styles/server-admin.css'
import './styles/antd-overrides.css'
import './styles/utilities.css'
import './styles/console.css'
import './styles/settings.css'
import App from './App.vue'
import router from './router'
import { applyTheme, detectTheme, useThemeStore } from './store/theme'
import { useSettingsStore } from './store/settings'
import { useAuthStore } from './store/auth'
import { installNoticeWatchdog } from './utils/notice-watchdog'
import { AUTH_TOKEN_KEY } from './api/auth'

// 在 mount 前同步主题，避免首屏按错误主题渲染后闪烁
applyTheme(detectTheme())

const app = createApp(App)
app.use(createPinia())
// 启动加载品牌抬头（规格书等组件容空，未加载完也不崩）。
// 匿名（无 token）跳过：公开页用不到它，且该请求 401 会触发跳 /login 打断公开路由。
if (localStorage.getItem(AUTH_TOKEN_KEY)) useSettingsStore().loadBranding()
// 启动恢复登录会话（token 存在则拉 /me；守卫里也会兜底）
useAuthStore().loadMe()
// 强制初始化 theme store，确保 ECharts 图表的 chartColors computed 拿到正确的 isDark 值
useThemeStore()
app.use(router)
installNoticeWatchdog()
app.mount('#app')
