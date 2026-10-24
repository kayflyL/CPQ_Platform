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
  chat_roles_allowed?: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(AUTH_TOKEN_KEY))
  const user = ref<AuthUser | null>(null)
  const permissions = ref<string[]>([])
  const loaded = ref(false)
  /** 办公室访问策略下还有可聊的 AI 角色（零角色账号隐藏全局浮动助手）。 */
  const chatRolesAllowed = ref(true)
  /** AUTH_ENABLED 灰度开关：false = 不强制登录、全部权限放行（旧行为）。 */
  const authEnabled = ref(true)
  const configLoaded = ref(false)

  const isAuthenticated = computed(() => !authEnabled.value || !!user.value)

  /** 价格字段键族（与后端 deps._PRICE_FAILCLOSED_KEYS 同源）：机密级 fail-closed，
   *  灰度期也不对无授权者开放——否则灰度下价格列/按钮照常渲染而数据被剥，体验割裂。 */
  const PRICE_FAILCLOSED_KEYS = ['field.quote.price', 'field.opportunity.quote_price', 'field.parts.price']

  /** 是否有某权限（menu/route/字段级 UI 统一入口）。灰度关闭时全放行；价格键族例外恒按授权判断。 */
  function can(key: string): boolean {
    if (!key) return true
    if (!authEnabled.value) return !PRICE_FAILCLOSED_KEYS.includes(key)
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
    chatRolesAllowed.value = res.chat_roles_allowed !== false
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
    chatRolesAllowed.value = true
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

  return { token, user, permissions, loaded, authEnabled, configLoaded, isAuthenticated, chatRolesAllowed, can, ensureConfig, login, logout, loadMe }
})
