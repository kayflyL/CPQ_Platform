// 办公室独立路由：桌面单路由 + 登录/权限守卫。/login、/forbidden 住 CPQ 入口，
// 跨入口跳转用整页导航（window.location），不做入口间 router 混跳。
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

export const OFFICE_BASE = '/office/'

const router = createRouter({
  history: createWebHistory(OFFICE_BASE),
  routes: [
    {
      path: '/',
      name: 'OfficeDesktop',
      component: () => import('@/views/office/AiOfficeView.vue'),
      meta: { title: 'AI 办公室', perm: 'page.office' },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureConfig()
  if (!auth.loaded) await auth.loadMe()
  if (!auth.isAuthenticated) {
    window.location.href = `/login?redirect=${encodeURIComponent(OFFICE_BASE)}`
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
