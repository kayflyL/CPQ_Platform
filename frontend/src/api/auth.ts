/**
 * Auth API client — login / me / change own password.
 * 自带独立实例并挂好鉴权拦截器（曾依赖 api/index.ts 给全局 axios 挂——但独立门面
 * /office/ 的导入图不含它，/me 裸奔 401 → 无限弹登录，2026-11-01 根治）。
 */
import axios from 'axios'
import { attachAuthInterceptors } from './authHttp'

export const AUTH_TOKEN_KEY = 'cpq_auth_token'

export interface AuthUser {
  user_id: string
  name: string
  email?: string
  role?: string
  is_active?: boolean
  created_at?: string
}

export interface LoginResult {
  token: string
  user: AuthUser
  permissions: string[]
  chat_roles_allowed?: boolean
}

export interface MeResult {
  user: AuthUser
  permissions: string[]
  chat_roles_allowed?: boolean
}

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

const http = axios.create()
attachAuthInterceptors(http)

export const authApi = {
  config: () => RESP<{ auth_enabled: boolean }>(http.get('/api/auth/config')),
  login: (username: string, password: string) =>
    RESP<LoginResult>(http.post('/api/auth/login', { username, password })),
  me: () => RESP<MeResult>(http.get('/api/auth/me')),
  changePassword: (old_password: string, new_password: string) =>
    RESP<{ success: boolean }>(http.put('/api/auth/password', { old_password, new_password })),
}
