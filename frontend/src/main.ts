import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import './styles/tokens.css'
import './styles/reset.css'
import './styles/glass.css'
import './styles/antd-overrides.css'
import './styles/utilities.css'
import './styles/console.css'
import App from './App.vue'
import router from './router'
import { applyTheme, detectTheme, useThemeStore } from './store/theme'

// 在 mount 前同步主题，避免首屏按错误主题渲染后闪烁
applyTheme(detectTheme())

const app = createApp(App)
app.use(createPinia())
// 强制初始化 theme store，确保 ECharts 图表的 chartColors computed 拿到正确的 isDark 值
useThemeStore()
app.use(router)
app.use(Antd)
app.mount('#app')