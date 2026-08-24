import type { AxiosInstance } from 'axios'
import { AUTH_TOKEN_KEY } from './auth'

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
      if (status === 401 && !url.includes('/api/auth/login')) {
        localStorage.removeItem(AUTH_TOKEN_KEY)
        if (!window.location.pathname.startsWith('/login')) {
          window.location.href = '/login'
        }
      }
      return Promise.reject(error)
    },
  )
}
