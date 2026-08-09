/**
 * Auth API client — login / me / change own password.
 * Token is stored by the auth store under AUTH_TOKEN_KEY; the axios
 * interceptor in api/index.ts attaches it to every request.
 */
import axios from 'axios'

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
}

export interface MeResult {
  user: AuthUser
  permissions: string[]
}

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export const authApi = {
  login: (username: string, password: string) =>
    RESP<LoginResult>(axios.post('/api/auth/login', { username, password })),
  me: () => RESP<MeResult>(axios.get('/api/auth/me')),
  changePassword: (old_password: string, new_password: string) =>
    RESP<{ success: boolean }>(axios.put('/api/auth/password', { old_password, new_password })),
}
