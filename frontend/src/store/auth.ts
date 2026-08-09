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

  const isAuthenticated = computed(() => !!user.value)

  /** 是否有某权限（menu/route/字段级 UI 统一入口）。 */
  function can(key: string): boolean {
    if (!key) return true
    return permissions.value.includes(key)
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

  return { token, user, permissions, loaded, isAuthenticated, can, login, logout, loadMe }
})
