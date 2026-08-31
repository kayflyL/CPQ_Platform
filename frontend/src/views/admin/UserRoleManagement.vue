<template>
  <div class="urm-page">
    <div class="urm-head">
      <h3>用户与权限</h3>
      <span class="urm-sub">角色、权限、账号均由这里维护，保存即时生效</span>
    </div>

    <a-tabs v-model:activeKey="tab">
      <!-- ── 角色管理 ── -->
      <a-tab-pane key="roles" tab="角色管理">
        <div class="toolbar">
          <a-button type="primary" @click="openCreateRole">+ 新建角色</a-button>
        </div>
        <a-table :data-source="roles" :columns="roleColumns" row-key="role_key" size="small" :loading="rolesLoading" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <span class="role-name">{{ record.name }}</span>
              <span v-if="record.role_key === 'admin'" class="role-tag">超级管理员</span>
            </template>
            <template v-else-if="column.key === 'permissions'">
              <span v-if="record.role_key === 'admin'" class="perm-count">全部（{{ catalog.length }}）</span>
              <span v-else class="perm-count">{{ record.permissions.length }} 项</span>
            </template>
            <template v-else-if="column.key === 'op'">
              <a-space>
                <a-button size="small" link @click="openEditRole(record)">编辑</a-button>
                <a-popconfirm title="删除该角色？" ok-text="删除" cancel-text="取消" @confirm="onDeleteRole(record)">
                  <a-button size="small" link danger :disabled="record.role_key === 'admin'">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- ── 用户管理 ── -->
      <a-tab-pane key="users" tab="用户管理">
        <div class="toolbar">
          <a-button type="primary" @click="openCreateUser">+ 新建用户</a-button>
        </div>
        <a-tabs v-model:activeKey="userGroupKey" size="small">
          <a-tab-pane v-for="tab in userGroupTabs" :key="tab.key" :tab="tab.label" />
        </a-tabs>
        <a-table :data-source="filteredUsers" :columns="userColumns" row-key="user_id" size="small" :loading="usersLoading" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'role'">
              <a-select
                :value="record.role"
                style="width: 180px"
                size="small"
                :options="roleOptions"
                @change="(v: string) => onRoleChange(record, v)"
              />
            </template>
            <template v-else-if="column.key === 'active'">
              <a-switch
                :checked="!!record.is_active"
                size="small"
                :disabled="record.name === 'admin'"
                @change="(v: boolean) => onActiveChange(record, v)"
              />
            </template>
            <template v-else-if="column.key === 'op'">
              <a-space>
                <a-button size="small" link :disabled="record.name === 'admin'" @click="openResetPwd(record)">重置密码</a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <!-- 角色编辑抽屉 -->
    <a-drawer
      :open="roleDrawer"
      @update:open="(v: boolean) => (roleDrawer = v)"
      :width="720"
      placement="right"
      :title="editingRoleKey ? '编辑角色' : '新建角色'"
    >
      <a-form layout="vertical">
        <a-form-item label="角色 key" required>
          <a-input v-model:value="roleForm.role_key" :disabled="!!editingRoleKey" placeholder="如 sales、manager（英文唯一标识）" />
        </a-form-item>
        <a-form-item label="角色名称" required>
          <a-input v-model:value="roleForm.name" placeholder="如 销售主管" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model:value="roleForm.description" placeholder="一句话说明这个角色的职责" />
        </a-form-item>
        <a-form-item label="权限">
          <div v-if="editingRoleKey === 'admin'" class="admin-note">管理员默认拥有全部权限（目录新增后自动生效），无需勾选。</div>
          <a-input
            v-if="editingRoleKey !== 'admin'"
            v-model:value="permSearch"
            allow-clear
            size="small"
            placeholder="搜索权限名称或 key"
            style="margin-bottom: 10px"
          />
          <a-collapse v-if="editingRoleKey !== 'admin'" v-model:activeKey="activeModules" :bordered="false">
            <a-collapse-panel v-for="g in permissionGroups" :key="g.group" :header="`${g.label}（${g.items.length}）`">
              <template #extra>
                <a-checkbox
                  :checked="isGroupAllChecked(g.items)"
                  :indeterminate="isGroupIndeterminate(g.items)"
                  @click.stop
                  @change="(e: any) => toggleGroup(g.items, e.target.checked)"
                >
                  全选
                </a-checkbox>
              </template>
              <div class="perm-list">
                <a-checkbox
                  v-for="p in g.items"
                  :key="p.key"
                  :checked="roleForm.permissions.includes(p.key)"
                  @change="(e: any) => togglePerm(p.key, e.target.checked)"
                >
                  {{ p.name }}<span class="perm-key">{{ p.key }}</span>
                </a-checkbox>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space>
          <a-button @click="roleDrawer = false">取消</a-button>
          <a-button type="primary" :loading="roleSaving" @click="saveRole">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 新建用户 -->
    <a-modal v-model:open="userModal" title="新建用户" :footer="null">
      <a-form layout="vertical">
        <a-form-item label="用户名" required>
          <a-input v-model:value="userForm.name" placeholder="登录用户名" />
        </a-form-item>
        <a-form-item label="初始密码" required>
          <a-input-password v-model:value="userForm.password" placeholder="至少 6 位" />
        </a-form-item>
        <a-form-item label="角色">
          <a-select v-model:value="userForm.role" :options="roleOptions" style="width: 100%" />
        </a-form-item>
        <a-form-item label="邮箱（可选）">
          <a-input v-model:value="userForm.email" placeholder="user@example.com" />
        </a-form-item>
        <a-space>
          <a-button @click="userModal = false">取消</a-button>
          <a-button type="primary" :loading="userSaving" @click="saveUser">创建</a-button>
        </a-space>
      </a-form>
    </a-modal>

    <!-- 重置密码 -->
    <a-modal v-model:open="resetPwdModal" title="重置密码" :footer="null">
      <p class="reset-tip">为 <b>{{ resetTarget?.name }}</b> 设置新密码（至少 6 位）</p>
      <a-form layout="vertical">
        <a-form-item label="新密码" required>
          <a-input-password v-model:value="resetPwd" placeholder="至少 6 位" />
        </a-form-item>
        <a-space>
          <a-button @click="resetPwdModal = false">取消</a-button>
          <a-button type="primary" :loading="userSaving" @click="confirmResetPwd">确认重置</a-button>
        </a-space>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { rbacApi, type PermissionItem, type RoleItem, type AdminUser } from '@/api/rbac'

const tab = ref('roles')

// ── 目录 / 角色 ──
const catalog = ref<PermissionItem[]>([])
const roles = ref<RoleItem[]>([])
const rolesLoading = ref(false)
const roleDrawer = ref(false)
const roleSaving = ref(false)
const editingRoleKey = ref<string | null>(null)
const permSearch = ref('')
const activeModules = ref<string[]>([])
const roleForm = ref<{ role_key: string; name: string; description: string; permissions: string[] }>({
  role_key: '', name: '', description: '', permissions: [],
})

const permissionGroups = computed(() => {
  const moduleOrder = ['工作台', '商机线索', '服务器', '配件', '解决方案', '设置']
  const keyword = permSearch.value.trim().toLowerCase()
  const groups: { group: string; label: string; items: PermissionItem[] }[] = []
  const used = new Set<string>()
  for (const module of moduleOrder) {
    const items = catalog.value.filter(p => {
      const moduleName = p.module || moduleOf(p)
      if (moduleName !== module) return false
      return !keyword || p.name.toLowerCase().includes(keyword) || p.key.toLowerCase().includes(keyword)
    })
    if (items.length) {
      groups.push({ group: module, label: module, items })
      used.add(module)
    }
  }
  const others = catalog.value.filter(p => {
    const moduleName = p.module || moduleOf(p)
    if (used.has(moduleName)) return false
    return !keyword || p.name.toLowerCase().includes(keyword) || p.key.toLowerCase().includes(keyword)
  })
  if (others.length) {
    groups.push({ group: '未分组', label: '未分组', items: others })
  }
  return groups
})

function moduleOf(p: PermissionItem): string {
  const prefixes: [string, string][] = [
    ['page.portal', '工作台'],
    ['page.opportunities', '商机线索'],
    ['page.servers', '服务器'],
    ['page.parts', '配件'],
    ['page.strategies', '解决方案'],
    ['page.settings', '设置'],
    ['field.quote', '工作台'],
    ['field.opportunity', '商机线索'],
    ['field.parts', '配件'],
    ['field.server', '服务器'],
    ['field.flow', '商机线索'],
    ['action.flow.return', '商机线索'],
  ]
  for (const [prefix, module] of prefixes) {
    if (p.key.startsWith(prefix)) return module
  }
  return '未分组'
}

function groupCheckedCount(items: PermissionItem[]): number {
  return items.filter(p => roleForm.value.permissions.includes(p.key)).length
}

function isGroupAllChecked(items: PermissionItem[]): boolean {
  return !!items.length && groupCheckedCount(items) === items.length
}

function isGroupIndeterminate(items: PermissionItem[]): boolean {
  const count = groupCheckedCount(items)
  return count > 0 && count < items.length
}

function toggleGroup(items: PermissionItem[], checked: boolean) {
  for (const p of items) {
    if (checked && !roleForm.value.permissions.includes(p.key)) {
      roleForm.value.permissions.push(p.key)
    } else if (!checked) {
      const i = roleForm.value.permissions.indexOf(p.key)
      if (i >= 0) roleForm.value.permissions.splice(i, 1)
    }
  }
}

const roleColumns = [
  { title: '角色 key', dataIndex: 'role_key', key: 'role_key', width: 140 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '描述', dataIndex: 'description', key: 'description' },
  { title: '权限', dataIndex: 'permissions', key: 'permissions', width: 90 },
  { title: '操作', key: 'op', width: 140 },
]

async function loadRoles() {
  rolesLoading.value = true
  try {
    roles.value = await rbacApi.roles.list()
  } catch {
    message.error('加载角色失败')
  } finally {
    rolesLoading.value = false
  }
}

function openCreateRole() {
  editingRoleKey.value = null
  roleForm.value = { role_key: '', name: '', description: '', permissions: [] }
  roleDrawer.value = true
}

function openEditRole(role: RoleItem) {
  editingRoleKey.value = role.role_key
  roleForm.value = {
    role_key: role.role_key,
    name: role.name,
    description: role.description || '',
    permissions: [...role.permissions],
  }
  roleDrawer.value = true
}

function togglePerm(key: string, checked: boolean) {
  const list = roleForm.value.permissions
  if (checked) {
    if (!list.includes(key)) list.push(key)
  } else {
    const i = list.indexOf(key)
    if (i >= 0) list.splice(i, 1)
  }
}

async function saveRole() {
  const f = roleForm.value
  if (!f.role_key.trim() || !f.name.trim()) {
    message.warning('角色 key 和名称不能为空')
    return
  }
  roleSaving.value = true
  try {
    if (editingRoleKey.value) {
      await rbacApi.roles.update(editingRoleKey.value, {
        name: f.name,
        description: f.description,
        permissions: f.permissions,
      })
      message.success('角色已更新')
    } else {
      await rbacApi.roles.create({ role_key: f.role_key.trim(), name: f.name.trim(), description: f.description, permissions: f.permissions })
      message.success('角色已创建')
    }
    roleDrawer.value = false
    await loadRoles()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    roleSaving.value = false
  }
}

async function onDeleteRole(role: RoleItem) {
  try {
    await rbacApi.roles.remove(role.role_key)
    message.success('角色已删除')
    await loadRoles()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

// ── 用户 ──
const users = ref<AdminUser[]>([])
const usersLoading = ref(false)
const userModal = ref(false)
const userSaving = ref(false)
const userForm = ref<{ name: string; password: string; role: string; email?: string }>({
  name: '', password: '', role: 'member', email: '',
})
const resetPwdModal = ref(false)
const resetPwd = ref('')
const resetTarget = ref<AdminUser | null>(null)

const roleOptions = computed(() => roles.value.map(r => ({ value: r.role_key, label: r.name })))

const userGroupKey = ref('all')
const userGroupTabs = computed(() => {
  const tabs = [{ key: 'all', label: '全部角色' }]
  const roleKeys = new Set(roles.value.map(r => r.role_key))
  for (const role of roles.value) {
    tabs.push({ key: role.role_key, label: role.name })
  }
  if (users.value.some(u => u.role && !roleKeys.has(u.role))) {
    tabs.push({ key: '__unassigned__', label: '未分配角色' })
  }
  return tabs
})
const filteredUsers = computed(() => {
  if (userGroupKey.value === 'all') return users.value
  if (userGroupKey.value === '__unassigned__') {
    const roleKeys = new Set(roles.value.map(r => r.role_key))
    return users.value.filter(u => !u.role || !roleKeys.has(u.role))
  }
  return users.value.filter(u => u.role === userGroupKey.value)
})

watch(userGroupTabs, tabs => {
  if (!tabs.some(t => t.key === userGroupKey.value)) {
    userGroupKey.value = 'all'
  }
}, { immediate: true })

const userColumns = [
  { title: '用户名', dataIndex: 'name', key: 'name' },
  { title: '角色', dataIndex: 'role', key: 'role', width: 200 },
  { title: '启用', dataIndex: 'is_active', key: 'active', width: 80 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '操作', key: 'op', width: 120 },
]

async function loadUsers() {
  usersLoading.value = true
  try {
    users.value = await rbacApi.users.list()
  } catch {
    message.error('加载用户失败')
  } finally {
    usersLoading.value = false
  }
}

function openCreateUser() {
  userForm.value = { name: '', password: '', role: 'member', email: '' }
  userModal.value = true
}

async function saveUser() {
  if (!userForm.value.name.trim() || userForm.value.password.length < 6) {
    message.warning('用户名不能为空，密码至少 6 位')
    return
  }
  userSaving.value = true
  try {
    await rbacApi.users.create({ ...userForm.value, name: userForm.value.name.trim() })
    message.success('用户已创建')
    userModal.value = false
    await loadUsers()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '创建失败')
  } finally {
    userSaving.value = false
  }
}

async function onRoleChange(user: AdminUser, role: string) {
  try {
    await rbacApi.users.update(user.user_id, { role })
    user.role = role
    message.success('角色已更新')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '更新失败')
    await loadUsers()
  }
}

async function onActiveChange(user: AdminUser, active: boolean) {
  try {
    await rbacApi.users.update(user.user_id, { is_active: active })
    user.is_active = active
    message.success(active ? '已启用' : '已禁用')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '更新失败')
    await loadUsers()
  }
}

function openResetPwd(user: AdminUser) {
  resetTarget.value = user
  resetPwd.value = ''
  resetPwdModal.value = true
}

async function confirmResetPwd() {
  if (!resetTarget.value || resetPwd.value.length < 6) {
    message.warning('密码至少 6 位')
    return
  }
  userSaving.value = true
  try {
    await rbacApi.users.update(resetTarget.value.user_id, { password: resetPwd.value })
    message.success('密码已重置')
    resetPwdModal.value = false
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '重置失败')
  } finally {
    userSaving.value = false
  }
}

onMounted(async () => {
  try {
    catalog.value = await rbacApi.permissions.list()
    activeModules.value = permissionGroups.value.map(g => g.group)
  } catch {
    /* 目录加载失败不阻塞页面 */
  }
  await Promise.all([loadRoles(), loadUsers()])
})
</script>

<style scoped>
.urm-page { padding: 16px; }
.urm-head { margin-bottom: 12px; }
.urm-head h3 { margin: 0 0 4px; }
.urm-sub { font-size: 12px; color: var(--cpq-text-muted, #6e7582); }
.toolbar { margin-bottom: 12px; }
.role-name { font-weight: 600; }
.role-tag {
  margin-left: 8px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--cpq-accent-primary, #1677ff);
  border: 1px solid currentColor;
}
.perm-count { color: var(--cpq-text-secondary, #9ba1aa); }
.perm-group { margin-bottom: 14px; }
.perm-group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary, #9ba1aa);
  margin-bottom: 6px;
}
.perm-list { display: flex; flex-direction: column; gap: 4px; }
.perm-key {
  margin-left: 6px;
  font-size: 11px;
  color: var(--cpq-text-muted, #6e7582);
  font-family: ui-monospace, monospace;
}
.admin-note {
  font-size: 12px;
  color: var(--cpq-text-muted, #6e7582);
  background: var(--cpq-overlay-w5, rgba(255,255,255,0.05));
  padding: 8px 10px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.reset-tip { color: var(--cpq-text-secondary, #9ba1aa); }
</style>
