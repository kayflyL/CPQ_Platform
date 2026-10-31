// 办公室独立路由：桌面单路由 + 登录/权限守卫。/login、/forbidden 住 CPQ 入口，
// 跨入口跳转用整页导航（window.location），不做入口间 router 混跳。
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

export const OFFICE_BASE = '/office/'

const router = createRouter({
  history: createWebHistory(OFFICE_BASE),
  routes: [
    {
      // 桌面（应用启动台）：进门第一屏
      path: '/',
      name: 'OfficeDesktop',
      component: () => import('@/views/office/OfficeDesktop.vue'),
      meta: { title: 'AI 办公室', perm: 'page.office' },
    },
    {
      // CPQ 应用工作区 = 现有 3D 办公室整体迁入（现状即视所得，只换地址）
      path: '/app/cpq',
      name: 'OfficeWorkspace',
      component: () => import('@/views/office/AiOfficeView.vue'),
      meta: { title: 'CPQ 办公室', perm: 'page.office' },
    },
    {
      // CPQ 系统设置页：⚙ 角标落地（权限卡 + 系统信息）
      path: '/app/cpq/settings',
      name: 'OfficeCpqSettings',
      component: () => import('@/views/office/OfficeCpqSettings.vue'),
      meta: { title: 'CPQ 系统设置', perm: 'page.office' },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureConfig()
  if (!auth.loaded) await auth.loadMe()
  if (!auth.isAuthenticated) {
    // 深链接保位：redirect = 门面根 + 路由内路径（/office/app/cpq/...）
    window.location.href = `/login?redirect=${encodeURIComponent(OFFICE_BASE + to.fullPath.replace(/^\//, ''))}`
    return false
  }
  // 页面级权限：无 page.office → CPQ 入口的 403 页
  const perm = to.meta?.perm as string | undefined
  if (perm && !auth.can(perm)) {
    window.location.href = '/forbidden'
    return false
  }
  return true
})

export default router
