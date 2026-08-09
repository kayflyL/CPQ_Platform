/**
 * Auth store — token + current user + permissions + login/logout/loadMe.
 * Permissions come from the backend (role → permission catalog) so role
 * definitions / assignments stay configurable (no hardcoded role list here).
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, AUTH_TOKEN_KEY, type AuthUser } from '@/api/auth'

export interface MeResult {
  user: AuthUser
  permissions: string[]
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(AUTH_TOKEN_KEY))
  const user = ref<AuthUser | null>(null)
  const permissions = ref<string[]>([])
  const loaded = ref(false)
  /** AUTH_ENABLED 灰度开关：false = 不强制登录、全部权限放行（旧行为）。 */
  const authEnabled = ref(true)
  const configLoaded = ref(false)

  const isAuthenticated = computed(() => !authEnabled.value || !!user.value)

  /** 是否有某权限（menu/route/字段级 UI 统一入口）。灰度关闭时全放行。 */
  function can(key: string): boolean {
    if (!authEnabled.value) return true
    if (!key) return true
    return permissions.value.includes(key)
  }

  /** 拉取 AUTH_ENABLED（只拉一次）。 */
  async function ensureConfig() {
    if (configLoaded.value) return
    try {
      const r = await authApi.config()
      authEnabled.value = r.auth_enabled
    } catch {
      authEnabled.value = true // 拉取失败按开启处理，安全优先
    } finally {
      configLoaded.value = true
    }
  }

  function applySession(res: MeResult) {
    user.value = res.user
    permissions.value = res.permissions || []
  }

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    token.value = res.token
    applySession(res)
    localStorage.setItem(AUTH_TOKEN_KEY, res.token)
  }

  function logout() {
    token.value = null
    user.value = null
    permissions.value = []
    loaded.value = false
    localStorage.removeItem(AUTH_TOKEN_KEY)
  }

  /** App boot: restore session from stored token (no token -> just mark loaded). */
  async function loadMe() {
    if (!token.value) {
      loaded.value = true
      return
    }
    try {
      const res = await authApi.me()
      applySession(res)
    } catch {
      logout() // token 失效/过期
    } finally {
      loaded.value = true
    }
  }

  return { token, user, permissions, loaded, authEnabled, configLoaded, isAuthenticated, can, ensureConfig, login, logout, loadMe }
})
