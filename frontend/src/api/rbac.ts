/**
 * RBAC API client — 权限目录 / 角色 CRUD / 用户管理。
 * 管理接口（/api/admin/*）由后端 admin 角色保护，前端仅作入口控制。
 */
import axios from 'axios'
import type { AuthUser } from './auth'

export interface PermissionItem {
  key: string
  name: string
  group: 'page' | 'field' | 'action'
  module?: string
}

export interface RoleItem {
  role_key: string
  name: string
  description?: string
  permissions: string[]
  updated_at?: string
}

export interface AdminUser extends AuthUser {
  role_name?: string
}

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export const rbacApi = {
  permissions: {
    list: () => RESP<{ permissions: PermissionItem[] }>(axios.get('/api/auth/permissions')).then(r => r.permissions),
    save: (permissions: PermissionItem[]) =>
      RESP<{ success: boolean }>(axios.put('/api/auth/permissions', { permissions })).then(r => r.success),
  },
  roles: {
    list: () => RESP<{ roles: RoleItem[] }>(axios.get('/api/admin/roles')).then(r => r.roles),
    create: (data: Omit<RoleItem, 'updated_at'>) =>
      RESP<{ role: RoleItem }>(axios.post('/api/admin/roles', data)).then(r => r.role),
    update: (roleKey: string, data: Partial<RoleItem>) =>
      RESP<{ role: RoleItem }>(axios.put(`/api/admin/roles/${encodeURIComponent(roleKey)}`, data)).then(r => r.role),
    remove: (roleKey: string) =>
      RESP<{ success: boolean }>(axios.delete(`/api/admin/roles/${encodeURIComponent(roleKey)}`)).then(r => r.success),
  },
  users: {
    list: () => RESP<{ users: AdminUser[] }>(axios.get('/api/admin/users')).then(r => r.users),
    create: (data: { name: string; password: string; role: string; email?: string }) =>
      RESP<{ user: AdminUser }>(axios.post('/api/admin/users', data)).then(r => r.user),
    update: (userId: string, data: { role?: string; is_active?: boolean; password?: string; name?: string }) =>
      RESP<{ success: boolean }>(axios.put(`/api/admin/users/${encodeURIComponent(userId)}`, data)).then(r => r.success),
  },
}
