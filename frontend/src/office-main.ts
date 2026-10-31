// AI 办公室独立入口（2026-11-01 形式独立）：office.html 只载办公室路由与页面，
// 与 CPQ 门面共享同一内核（后端 :8000）与同一登录态；共享代码（主题/鉴权/样式/
// 聊天运行时）按公共 chunk 复用，不复制。
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'ant-design-vue/dist/reset.css'
import './styles/tokens.css'
import './styles/reset.css'
import './styles/glass.css'
import './styles/antd-overrides.css'
import './styles/utilities.css'
import './styles/settings.css'
import './styles/office.css'
import App from './App.vue'
import OfficeRouter from './office-router'
// 全局 axios 拦截器显式挂载（CPQ 门面由 api/index.ts 代挂；办公室入口导入图
// 不含它——auth 客户端已自带实例，这里兜住其余裸 axios 调用：品牌抬头/通知看门狗）
import axios from 'axios'
import { attachAuthInterceptors } from './api/authHttp'
attachAuthInterceptors(axios)
import { applyTheme, detectTheme, useThemeStore } from './store/theme'
import { useSettingsStore } from './store/settings'
import { useAuthStore } from './store/auth'
import { installNoticeWatchdog } from './utils/notice-watchdog'
import { AUTH_TOKEN_KEY } from './api/auth'

// 在 mount 前同步主题，避免首屏按错误主题渲染后闪烁
applyTheme(detectTheme())

const app = createApp(App)
app.use(createPinia())
// 启动加载品牌抬头（未加载完也不崩）；匿名（无 token）跳过，防 401 打断
if (localStorage.getItem(AUTH_TOKEN_KEY)) useSettingsStore().loadBranding()
// 启动恢复登录会话（守卫里也会兜底）
useAuthStore().loadMe()
// 强制初始化 theme store，确保 ECharts/three 场景的 isDark 派生值正确
useThemeStore()
app.use(OfficeRouter)
installNoticeWatchdog()
app.mount('#app')
