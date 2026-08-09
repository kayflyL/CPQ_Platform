/**
 * Auth store — token + current user + login/logout/loadMe.
 * Permissions (RBAC) are layered on in the next step; here we only manage
 * identity so the router guard / menu can gate on "logged in".
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, AUTH_TOKEN_KEY, type AuthUser } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(AUTH_TOKEN_KEY))
  const user = ref<AuthUser | null>(null)
  const loaded = ref(false)

  const isAuthenticated = computed(() => !!user.value)

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    token.value = res.token
    user.value = res.user
    localStorage.setItem(AUTH_TOKEN_KEY, res.token)
  }

  function logout() {
    token.value = null
    user.value = null
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
      user.value = res.user
    } catch {
      logout() // token 失效/过期
    } finally {
      loaded.value = true
    }
  }

  return { token, user, loaded, isAuthenticated, login, logout, loadMe }
})
