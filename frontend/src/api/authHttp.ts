import type { AxiosInstance } from 'axios'
import { AUTH_TOKEN_KEY } from './auth'

/** 公开路径（公开目录/详情/配置向导/提交需求/根路径）：401 不劫持跳 /login——
 *  匿名与 stale-token 访客在这里由路由守卫接管（根路径应用内重定向到 /catalog）。 */
function isPublicPath(): boolean {
  const p = window.location.pathname
  return p === '/' || p.startsWith('/catalog') || p.startsWith('/lead')
}

/** 给独立 axios 实例统一附加 Bearer 请求头与 401 跳登录响应拦截。 */
export function attachAuthInterceptors(instance: AxiosInstance): void {
  instance.interceptors.request.use((config) => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY)
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  instance.interceptors.response.use(
    (response) => response,
    (error) => {
      const status = error?.response?.status
      const url: string = error?.config?.url || ''
      if (status === 401 && !url.includes('/api/auth/login') && !isPublicPath()) {
        localStorage.removeItem(AUTH_TOKEN_KEY)
        if (!window.location.pathname.startsWith('/login')) {
          // 带上当前地址，登录后原路返回（含 /office/ 独立门面）。曾为盲跳 /login：
          // 办公室守卫与这里的跳转赛跑时 redirect 参数被冲掉，登录完回不了办公室
          // ——「进办公室反复登录」的根因（2026-11-01）。
          const back = encodeURIComponent(window.location.pathname + window.location.search)
          window.location.href = `/login?redirect=${back}`
        }
      }
      return Promise.reject(error)
    },
  )
}
