<template>
  <div class="urm-page">
    <div class="urm-head">
      <h3>用户与权限</h3>
      <span class="urm-sub">角色、权限、账号均由这里维护，保存即时生效</span>
    </div>

    <!-- 页级 Tab -->
    <div class="glass page-tabs">
      <div class="page-tab" :class="{ active: tab === 'users' }" @click="tab = 'users'">
        用户管理 <span class="cnt">{{ users.length }}</span>
      </div>
      <div class="page-tab" :class="{ active: tab === 'roles' }" @click="tab = 'roles'">
        角色管理 <span class="cnt">{{ roles.length }}</span>
      </div>
    </div>

    <!-- ══ Tab 1 用户管理 ══ -->
    <div v-show="tab === 'users'" class="glass pane">
      <div class="toolbar">
        <div class="seg">
          <div class="seg-item" :class="{ active: userFilter === 'all' }" @click="userFilter = 'all'">
            全部 {{ users.length }}
          </div>
          <div class="seg-item" :class="{ active: userFilter === 'on' }" @click="userFilter = 'on'">
            已启用 {{ users.filter(u => u.is_active !== false).length }}
          </div>
          <div class="seg-item" :class="{ active: userFilter === 'off' }" @click="userFilter = 'off'">
            已停用 {{ users.filter(u => u.is_active === false).length }}
          </div>
        </div>
        <div class="search-box">
          <search-outlined style="color: var(--cpq-text-muted, #86909c)" />
          <input v-model="userSearch" placeholder="搜索姓名 / 企微ID" />
        </div>
        <div class="spacer"></div>
        <a-button type="primary" class="cta-btn" @click="openCreateUser">＋ 新建用户</a-button>
      </div>
      <a-table
        :data-source="filteredUsers"
        :columns="userColumns"
        row-key="user_id"
        size="middle"
        :loading="usersLoading"
        :pagination="userPagination"
        :custom-row="userRowProps"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'user'">
            <div class="cell-user">
              <div class="avatar" :style="{ background: avatarBg(record.name) }">{{ record.name.slice(0, 1) }}</div>
              <div>
                <div class="u-name">{{ record.name }}</div>
                <div class="u-sub">{{ record.wecom_userid || '企微未绑定' }}</div>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'role'">
            <span class="badge role-badge" :class="`role-${record.role || 'member'}`">
              <span class="dot" :style="{ background: roleColor(record.role) }"></span>{{ record.role_name || record.role || '未分配' }}
            </span>
          </template>
          <template v-else-if="column.key === 'last_active'">
            <span :class="{ stale: isStale(record) }">{{ lastActiveText(record) }}</span>
          </template>
          <template v-else-if="column.key === 'active'">
            <span class="badge" :class="record.is_active !== false ? 'on' : 'off'">
              <span class="dot" :style="{ background: record.is_active !== false ? 'var(--cpq-color-success, #52C9A0)' : 'var(--cpq-text-disabled, #c9cdd4)' }"></span>{{ record.is_active !== false ? '启用' : '停用' }}
            </span>
          </template>
          <template v-else-if="column.key === 'op'">
            <a-dropdown :trigger="['click']" placement="bottomRight">
              <button class="op-btn" @click.stop>⋯</button>
              <template #overlay>
                <a-menu @click="({ key }: any) => onUserMenu(key, record)">
                  <a-menu-item key="detail">查看详情</a-menu-item>
                  <a-menu-item key="reset" :disabled="record.name === 'admin'">重置密码</a-menu-item>
                  <a-menu-item key="toggle">
                    {{ record.is_active !== false ? '停用账号' : '启用账号' }}
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="delete" danger :disabled="record.role === 'admin' || record.user_id === auth.user?.user_id">
                    删除用户…
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </template>
      </a-table>
    </div>

    <!-- ══ Tab 2 角色管理 ══ -->
    <div v-show="tab === 'roles'" class="glass pane">
      <div class="toolbar">
        <span class="hint-text">角色 = 一组权限的集合；内置角色覆盖日常，需要时从最接近的角色复制微调。</span>
        <div class="spacer"></div>
        <a-button type="primary" class="cta-btn" @click="openCreateRole">＋ 新建角色</a-button>
      </div>
      <a-table
        :data-source="roles"
        :columns="roleColumns"
        row-key="role_key"
        size="middle"
        :loading="rolesLoading"
        :pagination="false"
        :custom-row="roleRowProps"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <div class="role-name">{{ record.name }}<span v-if="record.role_key === 'admin'" class="badge role-admin" style="margin-left: 8px">超级管理员</span><span v-else-if="isBuiltin(record.role_key)" class="badge builtin" style="margin-left: 8px">内置</span></div>
            <div class="role-desc">{{ record.description || '—' }}</div>
          </template>
          <template v-else-if="column.key === 'members'">
            <span class="link-num" @click.stop="openRoleMembers(record)">{{ memberCount(record.role_key) }} 人</span>
          </template>
          <template v-else-if="column.key === 'permissions'">
            <template v-if="record.role_key === 'admin'">
              <span class="perm-count">全部（{{ catalog.length }}）</span>
            </template>
            <template v-else>
              <span class="perm-dots"><i v-for="n in Math.min(record.permissions.length, 8)" :key="n"></i></span>
              <span class="perm-count" style="margin-left: 6px">{{ record.permissions.length }} 项</span>
            </template>
          </template>
          <template v-else-if="column.key === 'op'">
            <a-dropdown :trigger="['click']" placement="bottomRight">
              <button class="op-btn" @click.stop>⋯</button>
              <template #overlay>
                <a-menu @click="({ key }: any) => onRoleMenu(key, record)">
                  <a-menu-item key="edit">编辑权限</a-menu-item>
                  <a-menu-item key="members">查看成员</a-menu-item>
                  <a-menu-item key="copy">复制此角色</a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="delete" danger :disabled="isBuiltin(record.role_key)" :title="isBuiltin(record.role_key) ? '内置角色不可删除' : ''">
                    删除角色
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </template>
      </a-table>
    </div>

    <!-- ══ 用户详情抽屉 ══ -->
    <a-drawer
      :open="userDrawer"
      @close="userDrawer = false"
      width="460"
      placement="right"
      :title="null"
      root-class-name="urm-drawer"
    >
      <template #title>
        <div class="drawer-user-head">
          <div class="avatar lg" :style="{ background: avatarBg(detailUser?.name || '') }">{{ (detailUser?.name || '').slice(0, 1) }}</div>
          <div>
            <div class="u-name lg">{{ detailUser?.name }}</div>
            <div style="margin-top: 4px">
              <span class="badge role-badge" :class="`role-${detailUser?.role || 'member'}`">
                <span class="dot" :style="{ background: roleColor(detailUser?.role) }"></span>{{ detailUser?.role_name || detailUser?.role || '未分配' }}
              </span>
              <span class="badge" :class="detailUser?.is_active !== false ? 'on' : 'off'" style="margin-left: 6px">
                <span class="dot" :style="{ background: detailUser?.is_active !== false ? 'var(--cpq-color-success, #52C9A0)' : 'var(--cpq-text-disabled, #c9cdd4)' }"></span>{{ detailUser?.is_active !== false ? '启用' : '停用' }}
              </span>
            </div>
          </div>
        </div>
      </template>
      <div v-if="detailUser" class="drawer-sec">
        <h4>账号信息</h4>
        <dl class="kv">
          <dt>企微 ID</dt>
          <dd>
            <a-input
              :value="detailUser.wecom_userid || ''"
              size="small"
              style="width: 200px"
              placeholder="企微 userid"
              @blur="(e: FocusEvent) => onWecomSave(detailUser!, (e.target as HTMLInputElement).value)"
              @press-enter="($event.target as HTMLInputElement).blur()"
            />
          </dd>
          <dt>最近活跃</dt>
          <dd :class="{ stale: isStale(detailUser) }">{{ lastActiveText(detailUser) }}</dd>
          <dt>创建时间</dt>
          <dd>{{ (detailUser.created_at || '—').slice(0, 10) }}</dd>
        </dl>
      </div>
      <div class="drawer-sec">
        <h4>角色</h4>
        <a-select
          :value="detailUser?.role || 'member'"
          style="width: 100%"
          :options="rolePickOptions"
          @change="(v: string) => detailUser && onRoleChange(detailUser, v)"
        />
        <div class="role-hint">改角色即时生效；商机归属与流程指派不受影响。</div>
      </div>
      <div class="drawer-sec">
        <h4>操作</h4>
        <a-space>
          <a-button size="small" :disabled="detailUser?.name === 'admin'" @click="detailUser && openResetPwd(detailUser)">重置密码</a-button>
          <a-button size="small" :disabled="detailUser?.name === 'admin'" @click="detailUser && onActiveChange(detailUser, detailUser.is_active === false)">
            {{ detailUser?.is_active !== false ? '停用账号' : '启用账号' }}
          </a-button>
        </a-space>
      </div>
      <div class="danger-zone">
        <h4>危险区</h4>
        <p>删除将转移该用户的商机归属、流程指派与通知给指定接手人，操作不可撤销。历史留痕（创建记录/上传记录）保留原文。</p>
        <a-button danger :disabled="detailUser?.role === 'admin' || detailUser?.user_id === auth.user?.user_id" @click="detailUser && openDeleteUser(detailUser)">
          删除用户…
        </a-button>
      </div>
    </a-drawer>

    <!-- ══ 角色抽屉（底版+增量 / 列表·网格双视图 / 已授权成员）══ -->
    <a-drawer
      :open="roleDrawer"
      @close="roleDrawer = false"
      width="1080"
      placement="right"
      root-class-name="urm-drawer"
    >
      <template #title>
        <div>
          <div class="u-name lg">
            {{ roleForm.name || (editingRoleKey ? '编辑角色' : '新建角色') }}
            <span v-if="editingRoleKey && isBuiltin(editingRoleKey)" class="badge builtin" style="margin-left: 6px">内置</span>
          </div>
          <div class="role-desc" style="margin-top: 2px">
            {{ roleForm.description || '一句话说明这个角色的职责' }}
            <template v-if="editingRoleKey"> · {{ memberCount(editingRoleKey) }} 名成员</template>
          </div>
        </div>
      </template>

      <div class="role-ed-layout">
        <!-- 主列 -->
        <div class="role-ed-main">
          <div v-if="editingRoleKey" class="drawer-tabs">
            <div class="drawer-tab" :class="{ active: roleTab === 'perms' }" @click="roleTab = 'perms'">权限配置</div>
            <div class="drawer-tab" :class="{ active: roleTab === 'members' }" @click="roleTab = 'members'">
              已授权成员 <span style="color: var(--cpq-text-muted, #86909c)">{{ memberCount(editingRoleKey) }}</span>
            </div>
          </div>

          <!-- 已授权成员 -->
          <div v-if="editingRoleKey && roleTab === 'members'" class="drawer-sec">
            <div v-for="u in roleMembers" :key="u.user_id" class="member-row">
              <div class="avatar" :style="{ background: avatarBg(u.name) }">{{ u.name.slice(0, 1) }}</div>
              <div class="grow">
                {{ u.name }}
                <span class="mut">· {{ lastActiveText(u) }}</span>
              </div>
              <a-button size="small" type="text" danger @click="removeRoleMember(u)">移除</a-button>
            </div>
            <div v-if="!roleMembers.length" class="perm-empty">该角色暂无成员</div>
            <div style="text-align: center; margin-top: 12px">
              <a-button size="small" @click="openAddMember">＋ 添加成员</a-button>
            </div>
          </div>

          <!-- 权限配置 -->
          <div v-else class="drawer-sec">
            <div v-if="editingRoleKey === 'admin'" class="admin-note">管理员默认拥有全部权限（目录新增后自动生效），无需勾选。</div>
            <template v-else>
              <!-- ① 底版选择 -->
              <div v-if="awaitingBase" class="rel">
                <div class="steps">
                  <div class="step cur"><span class="n">1</span>选底版</div>
                  <div class="step"><span class="n">2</span>调增量</div>
                  <div class="step" :class="formReady ? 'done' : ''"><span class="n">{{ formReady ? '✓' : '3' }}</span>命名保存</div>
                </div>
                <div class="base-title">选择底版 —— 角色从最接近的内置角色起步</div>
                <div class="base-grid">
                  <div v-for="b in baseChoices" :key="b.key" class="base-card" :class="{ sel: b.key === baseKey }" @click="pickBase(b.key)">
                    <div class="nm"><span class="dot" :style="{ background: b.color }"></span>{{ b.name }}</div>
                    <div class="ds">{{ b.desc }}</div>
                    <div class="ct">{{ b.perms.length }} 项权限</div>
                  </div>
                </div>
              </div>

              <!-- ② 调增量 -->
              <template v-else>
                <div class="rel">
                  <div class="steps" v-if="!editingRoleKey">
                    <div class="step done"><span class="n">✓</span>选底版</div>
                    <div class="step cur"><span class="n">2</span>调增量</div>
                    <div class="step" :class="formReady ? 'done' : ''"><span class="n">{{ formReady ? '✓' : '3' }}</span>命名保存</div>
                  </div>
                  <div class="diff-bar">
                    <span class="base-name"><span class="dot" :style="{ background: baseChoice?.color }"></span>基于「{{ baseChoice?.name }}」</span>
                    <span class="muted">· 基础 {{ baseChoice?.perms.length || 0 }} 项</span>
                    <span class="d-add">＋{{ diff.added.length }} 增量</span>
                    <span class="d-cut">−{{ diff.cut.length }} 减项</span>
                    <span class="muted">= 当前 <b>{{ roleForm.permissions.length }}</b> 项</span>
                    <span class="link" @click="awaitingBase = true">换底版 / 复制其他角色</span>
                  </div>
                  <div class="diff-chips">
                    <span v-for="p in diff.added" :key="p.key" class="dchip add">＋ {{ shortOf(p) }}<i class="x" @click="togglePerm(p.key, false)">✕</i></span>
                    <span v-for="p in diff.cut" :key="p.key" class="dchip cut">− {{ shortOf(p) }}<i class="x" @click="togglePerm(p.key, true)">✕</i></span>
                    <span v-if="!diff.added.length && !diff.cut.length" class="dchip none">与「{{ baseChoice?.name }}」完全一致 —— 勾掉一项就会出现在这里</span>
                  </div>
                  <div class="note-anchor-stub" style="display:none"></div>

                  <div class="view-toggle">
                    <div class="vt" :class="{ active: editorView === 'list' }" @click="editorView = 'list'">列表视图</div>
                    <div class="vt" :class="{ active: editorView === 'grid' }" @click="editorView = 'grid'">网格视图（模块 × 动作）</div>
                  </div>

                  <!-- 列表视图 -->
                  <div v-show="editorView === 'list'">
                    <a-input v-model:value="permSearch" allow-clear size="small" placeholder="搜索权限名称或 key…" style="margin-bottom: 12px" />
                    <div v-for="cat in permCats" :key="cat.key" class="perm-cat">
                      <div class="perm-cat-title">{{ cat.icon }} {{ cat.label }}</div>
                      <div v-for="g in catGroups(cat.key)" :key="g.group" class="perm-group">
                        <div class="perm-group-head">
                          {{ g.label }} <span class="cnt">（{{ g.items.length }}）</span>
                          <label class="chk">
                            <input
                              type="checkbox"
                              :checked="isGroupAllChecked(g.items)"
                              :indeterminate.prop="isGroupIndeterminate(g.items)"
                              @change="(e: any) => toggleGroup(g.items, e.target.checked)"
                            />全选
                          </label>
                        </div>
                        <div class="perm-items">
                          <label v-for="p in g.items" :key="p.key" class="perm-item" :class="{ cut: isBasePerm(p.key) && !roleForm.permissions.includes(p.key) }">
                            <input
                              type="checkbox"
                              :checked="roleForm.permissions.includes(p.key)"
                              @change="(e: any) => togglePerm(p.key, e.target.checked)"
                            />
                            <div>
                              <div class="label">
                                {{ p.name }}
                                <span v-if="isBasePerm(p.key) && roleForm.permissions.includes(p.key)" class="tag base">基础</span>
                                <span v-else-if="!isBasePerm(p.key) && roleForm.permissions.includes(p.key)" class="tag add">＋增量</span>
                                <span v-else-if="isBasePerm(p.key)" class="tag base">底版划掉</span>
                              </div>
                              <div class="key">{{ p.key }}</div>
                            </div>
                          </label>
                        </div>
                      </div>
                      <div v-if="!catGroups(cat.key).length" class="perm-empty">无匹配权限</div>
                    </div>
                  </div>

                  <!-- 网格视图 -->
                  <div v-show="editorView === 'grid'" class="grid-wrap">
                    <table class="grid">
                      <thead><tr><th>模块 ＼ 动作</th><th v-for="a in ACT_ORDER" :key="a">{{ a }}</th></tr></thead>
                      <tbody>
                        <tr v-for="row in gridRows" :key="row.mod">
                          <th>{{ row.mod }}</th>
                          <td v-for="(cell, ci) in row.cells" :key="ci">
                            <template v-if="cell.length">
                              <label v-for="p in cell" :key="p.key" class="gitem" :class="{ cut: isBasePerm(p.key) && !roleForm.permissions.includes(p.key) }">
                                <input
                                  type="checkbox"
                                  :checked="roleForm.permissions.includes(p.key)"
                                  @change="(e: any) => togglePerm(p.key, e.target.checked)"
                                />
                                <span class="lb">
                                  {{ shortOf(p) }}<span v-if="!isBasePerm(p.key) && roleForm.permissions.includes(p.key)" class="tag add">＋</span>
                                </span>
                              </label>
                            </template>
                            <span v-else class="gcell-none">—</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
                </template>
              </template>
            </div>

        <!-- 侧栏：角色信息 + 保存前预览 -->
        <div class="role-ed-side">
          <h4>角色信息</h4>
          <div class="form-item">
            <label>角色 key（英文唯一标识）</label>
            <a-input v-model:value="roleForm.role_key" size="small" :disabled="!!editingRoleKey" placeholder="如 sales_lead" />
          </div>
          <div class="form-item">
            <label>角色名称</label>
            <a-input v-model:value="roleForm.name" size="small" placeholder="如 销售主管" />
          </div>
          <div class="form-item">
            <label>描述</label>
            <a-input v-model:value="roleForm.description" size="small" placeholder="一句话职责说明" />
          </div>
          <h4 style="margin-top: 16px">保存前预览</h4>
          <div class="preview-card">
            <div class="row"><span>权限总数</span><span class="v">{{ previewStats.total }} 项</span></div>
            <div class="row"><span>等价于</span><span class="v">{{ previewStats.equiv }}</span></div>
            <div class="row"><span>覆盖模块</span><span class="v">{{ previewStats.modules }}</span></div>
            <div class="row"><span>敏感权限</span><span class="v">{{ previewStats.sensitive }} 项</span></div>
          </div>
          <div class="side-note">保存的永远是<b style="color: var(--cpq-accent-primary, #1677ff)">最终权限集合</b>——底版只是编辑时的参照，与底版角色各自独立演进、互不影响。</div>
        </div>
      </div>
    </div>

      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button @click="roleDrawer = false">取消</a-button>
          <a-button type="primary" :loading="roleSaving" @click="saveRole">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 添加成员弹窗（角色抽屉） -->
    <a-modal v-model:open="addMemberOpen" title="添加成员" :footer="null" width="420px">
      <a-input v-model:value="addMemberSearch" allow-clear size="small" placeholder="搜索用户…" style="margin-bottom: 8px" />
      <div v-for="u in addMemberCandidates" :key="u.user_id" class="member-row">
        <div class="avatar" :style="{ background: avatarBg(u.name) }">{{ u.name.slice(0, 1) }}</div>
        <div class="grow">{{ u.name }} <span class="mut">· {{ u.role_name || u.role || '未分配' }}</span></div>
        <a-button size="small" type="link" @click="addRoleMember(u)">加入</a-button>
      </div>
      <div v-if="!addMemberCandidates.length" class="perm-empty">没有可添加的用户</div>
    </a-modal>

    <!-- 新建用户 -->
    <a-modal v-model:open="userModal" title="新建用户" :footer="null">
      <a-form layout="vertical">
        <a-form-item label="用户名（登录名）" required>
          <a-input v-model:value="userForm.name" placeholder="登录用户名" @keydown.enter="saveUser" />
        </a-form-item>
        <a-form-item label="初始密码（至少 6 位，首登后可自行修改）" required>
          <a-input-password v-model:value="userForm.password" placeholder="至少 6 位" @keydown.enter="saveUser" />
        </a-form-item>
        <a-form-item label="角色">
          <a-select v-model:value="userForm.role" :options="rolePickOptions" />
        </a-form-item>
        <a-form-item label="企微 ID（选填，用于通知推送）">
          <a-input v-model:value="userForm.wecom_userid" placeholder="企微 userid" @keydown.enter="saveUser" />
        </a-form-item>
        <a-space style="display: flex; justify-content: flex-end">
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

    <!-- 删除用户：先看引用，再选转接人 -->
    <a-modal v-model:open="deleteModal" title="删除用户" :footer="null" :width="560">
      <p class="reset-tip">
        删除 <b>{{ deleteUser?.name }}</b>
        <a-tag v-if="functionalCount > 0" color="warning">有 {{ functionalCount }} 条功能性引用待转接</a-tag>
        <a-tag v-else color="success">无功能性引用，可直接删除</a-tag>
      </p>
      <div v-if="deleteRefs">
        <p v-if="functionalCount" style="margin: 4px 0 8px; font-weight: 600">转接后删除（将改挂到转接人名下）：</p>
        <ul v-if="functionalCount" class="ref-list">
          <li v-for="(n, k) in deleteRefs.functional" :key="k">{{ refLabel(String(k)) }}：{{ n }} 条</li>
        </ul>
        <p style="margin: 8px 0 4px; color: var(--cpq-text-muted, #86909c)">历史留痕（保留原文，不转接）：</p>
        <ul class="ref-list muted">
          <li v-for="(n, k) in deleteRefs.historical" :key="k">{{ refLabel(String(k)) }}：{{ n }} 条</li>
          <li v-if="!Object.keys(deleteRefs.historical).length">无</li>
        </ul>
      </div>
      <a-form layout="vertical" style="margin-top: 12px">
        <a-form-item
          v-if="functionalCount > 0"
          label="转接人 —— 其商机归属 / 流程指派 / 通知将改挂到该用户名下"
          required
        >
          <a-select
            v-model:value="deleteTransferTo"
            :options="transferOptions"
            show-search
            option-filter-prop="label"
            placeholder="选择接手该用户业务的人"
          />
        </a-form-item>
        <a-space>
          <a-button @click="deleteModal = false">取消</a-button>
          <a-button danger type="primary" :loading="deleteLoading" @click="confirmDeleteUser">确认删除</a-button>
        </a-space>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { SearchOutlined } from '@ant-design/icons-vue'
import { rbacApi, type PermissionItem, type RoleItem, type AdminUser } from '@/api/rbac'
import { useAuthStore } from '@/store/auth'
import { formatRelativeTime } from '@/utils/relativeTime'

const auth = useAuthStore()
const tab = ref<'users' | 'roles'>('users')

// ── 目录 / 角色 ──
const catalog = ref<PermissionItem[]>([])
const roles = ref<RoleItem[]>([])
const rolesLoading = ref(false)
const roleDrawer = ref(false)
const roleSaving = ref(false)
const editingRoleKey = ref<string | null>(null)
const roleTab = ref<'perms' | 'members'>('perms')
const permSearch = ref('')
const roleForm = ref<{ role_key: string; name: string; description: string; permissions: string[] }>({
  role_key: '', name: '', description: '', permissions: [],
})

const BUILTIN_ROLE_KEYS = ['admin', 'business', 'te', 'quote', 'cost', 'director']

function isBuiltin(roleKey: string): boolean {
  return BUILTIN_ROLE_KEYS.includes(roleKey)
}

function memberCount(roleKey: string): number {
  return users.value.filter(u => (u.role || 'member') === roleKey).length
}

function roleColor(role?: string): string {
  const map: Record<string, string> = {
    admin: 'var(--cpq-color-purple, #a855f7)',
    business: 'var(--cpq-accent-primary, #1677FF)',
    quote: 'var(--cpq-color-success, #52C9A0)',
    te: 'var(--cpq-notif-cyan, #0ea5b7)',
    cost: 'var(--cpq-color-gold, #d4a853)',
    director: 'var(--cpq-color-gold, #d4a853)',
    member: 'var(--cpq-text-muted, #86909c)',
  }
  return map[role || 'member'] || map.member
}

function avatarBg(name: string): string {
  let h = 0
  for (const ch of name || '') h = (h + ch.charCodeAt(0)) % 360
  return `linear-gradient(135deg, hsl(${h}, 70%, 55%), hsl(${(h + 40) % 360}, 70%, 45%))`
}

// ── 权限目录：三类语义分组（page/field/action）× 模块二级 ──
const PERM_CATS = [
  { key: 'page', label: '页面权限（page）', icon: '🗂' },
  { key: 'field', label: '字段可见（field）', icon: '👁' },
  { key: 'action', label: '操作权限（action）', icon: '⚡' },
] as const
const permCats = PERM_CATS

const MODULE_ORDER = ['商机线索', '商机线索 · 商机详情', '商机线索 · 报价工作台', 'AI 办公室', '服务器', '配件', '解决方案', '设置']

function moduleOf(p: PermissionItem): string {
  const prefixes: [string, string][] = [
    ['page.opportunities_all', '商机线索'],
    ['page.opportunities', '商机线索'],
    ['field.opportunity', '商机线索 · 商机详情'],
    ['field.flow', '商机线索 · 商机详情'],
    ['action.flow.return.quoting', '商机线索 · 报价工作台'],
    ['action.flow.submit.quoting', '商机线索 · 报价工作台'],
    ['action.quote', '商机线索 · 报价工作台'],
    ['field.quote', '商机线索 · 报价工作台'],
    ['action.flow', '商机线索 · 商机详情'],
    ['page.office', 'AI 办公室'],
    ['ai.office', 'AI 办公室'],
    ['page.servers', '服务器'],
    ['page.parts', '配件'],
    ['page.strategies', '解决方案'],
    ['page.settings', '设置'],
  ]
  for (const [prefix, module] of prefixes) {
    if (p.key.startsWith(prefix)) return module
  }
  return '未分组'
}

function catGroups(catKey: string): { group: string; label: string; items: PermissionItem[] }[] {
  const keyword = permSearch.value.trim().toLowerCase()
  const hit = (p: PermissionItem) =>
    !keyword || p.name.toLowerCase().includes(keyword) || p.key.toLowerCase().includes(keyword)
  const groups: { group: string; label: string; items: PermissionItem[] }[] = []
  const used = new Set<string>()
  for (const module of MODULE_ORDER) {
    const items = catalog.value.filter(p => {
      if (p.group !== catKey) return false
      const moduleName = p.module || moduleOf(p)
      if (moduleName !== module) return false
      return hit(p)
    })
    if (items.length) {
      groups.push({ group: module, label: module, items })
      used.add(module)
    }
  }
  const others = catalog.value.filter(p => {
    if (p.group !== catKey) return false
    const moduleName = p.module || moduleOf(p)
    if (used.has(moduleName)) return false
    return hit(p)
  })
  if (others.length) groups.push({ group: '未分组', label: '未分组', items: others })
  return groups
}

const coveredModules = computed(() => {
  const mods = new Set<string>()
  for (const key of roleForm.value.permissions) {
    const p = catalog.value.find(c => c.key === key)
    if (p) mods.add(p.module || moduleOf(p))
  }
  return [...mods]
})

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

function togglePerm(key: string, checked: boolean) {
  const list = roleForm.value.permissions
  if (checked) {
    if (!list.includes(key)) list.push(key)
  } else {
    const i = list.indexOf(key)
    if (i >= 0) list.splice(i, 1)
  }
}

const roleColumns = [
  { title: '角色', key: 'name' },
  { title: '成员', key: 'members', width: 90 },
  { title: '权限', key: 'permissions', width: 170 },
  { title: '操作', key: 'op', width: 60 },
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

// ── 底版（基础档）+ Diff + 网格视图 ──
const awaitingBase = ref(false)
const baseKey = ref('blank')
const editorView = ref<'list' | 'grid'>('list')

const baseChoices = computed(() => [
  { key: 'blank', name: '空白', color: 'var(--cpq-text-muted, #86909c)', desc: '从零勾选，不建议', perms: [] as string[] },
  ...roles.value
    .filter(r => isBuiltin(r.role_key) && r.role_key !== 'admin')
    .map(r => ({ key: r.role_key, name: r.name, color: roleColor(r.role_key), desc: r.description || '', perms: r.permissions })),
])
const baseChoice = computed(() => baseChoices.value.find(b => b.key === baseKey.value))

function autoBaseFor(perms: string[]): string {
  let best = 'blank'
  let bestScore = 0
  for (const b of baseChoices.value) {
    if (b.key === 'blank') continue
    const overlap = b.perms.filter(k => perms.includes(k)).length
    const score = b.perms.length ? overlap / Math.max(b.perms.length, perms.length) : 0
    if (score > bestScore) { bestScore = score; best = b.key }
  }
  return bestScore >= 0.5 ? best : 'blank'
}

function isBasePerm(key: string): boolean {
  return (baseChoice.value?.perms || []).includes(key)
}

const diff = computed(() => {
  const base = new Set(baseChoice.value?.perms || [])
  const keyOf = (k: string) => catalog.value.find(c => c.key === k)
  return {
    added: roleForm.value.permissions.filter(k => !base.has(k)).map(keyOf).filter(Boolean) as PermissionItem[],
    cut: [...base].filter(k => !roleForm.value.permissions.includes(k)).map(keyOf).filter(Boolean) as PermissionItem[],
  }
})

function pickBase(key: string) {
  if (key === baseKey.value) { awaitingBase.value = false; return }
  const target = baseChoices.value.find(b => b.key === key)
  const untouched = diff.value.added.length === 0 && diff.value.cut.length === 0
  const apply = (resetPerms: boolean) => {
    baseKey.value = key
    if (resetPerms) roleForm.value.permissions = [...(target?.perms || [])]
    awaitingBase.value = false
  }
  if (untouched) { apply(true); return }
  Modal.confirm({
    title: `切换底版为「${target?.name}」？`,
    content: '当前权限相对底版已有调整。',
    okText: '重置为其权限集合',
    cancelText: '仅换对比基准',
    onOk: () => apply(true),
    onCancel: () => apply(false),
  })
}

const formReady = computed(() => !!(roleForm.value.role_key.trim() && roleForm.value.name.trim()))

// 网格视图：行=模块 × 列=动作
const ACT_ORDER = ['页面', '字段可见', '提交', '退回', '审批·其他']
function actOf(p: PermissionItem): string {
  if (p.group === 'page') return '页面'
  if (p.group === 'field') return '字段可见'
  if (p.key.startsWith('action.flow.submit.')) return '提交'
  if (p.key.startsWith('action.flow.return.')) return '退回'
  return '审批·其他'
}
const gridRows = computed(() => {
  const rows: { mod: string; cells: PermissionItem[][] }[] = []
  const seen = new Set<string>()
  const push = (mod: string) => {
    if (seen.has(mod)) return
    seen.add(mod)
    const items = catalog.value.filter(p => (p.module || moduleOf(p)) === mod)
    if (!items.length) return
    rows.push({ mod, cells: ACT_ORDER.map(a => items.filter(p => actOf(p) === a)) })
  }
  MODULE_ORDER.forEach(push)
  catalog.value.forEach(p => push(p.module || moduleOf(p)))
  return rows
})

const SHORT_LABELS: Record<string, string> = {
  'page.opportunities_all': '线索菜单(全量)',
  'page.opportunities': '商机子页面',
  'field.opportunity.quote_price': '报价金额',
  'field.flow.bom': '方案附件',
  'field.flow.cost': '成本附件',
  'action.flow.submit.requirement': '提交需求单',
  'action.opportunity.result': '改商机状态',
  'action.flow.submit.boming': '提交方案',
  'action.flow.return.boming': '退回方案',
  'action.flow.submit.costing': '提交成本',
  'action.flow.return.costing': '退回成本',
  'action.flow.approve.pricing': '低毛利审批',
  'field.quote.price': '整机/配件价格',
  'field.quote.export_internal': '对内版导出',
  'action.flow.submit.quoting': '发送报价',
  'action.flow.return.quoting': '退回报价',
  'action.quote.unfreeze': '解冻报价',
  'page.office': '办公室页面',
  'ai.office.manage': '管员工/团队',
  'ai.office.admin': '管模型/接入',
  'page.servers': '服务器页面',
  'page.parts': '配件页面',
  'page.strategies': '解决方案页',
  'page.settings.users': '用户与权限',
  'page.settings.excel': '解析规则',
  'page.settings.templates': '导出模板',
  'page.settings.admin': '服务器管理',
}
function shortOf(p: PermissionItem): string {
  return SHORT_LABELS[p.key] || (p.name.length > 10 ? p.name.slice(0, 10) + '…' : p.name)
}

const previewStats = computed(() => {
  const { added, cut } = diff.value
  const b = baseChoice.value
  const equiv = added.length || cut.length
    ? `「${b?.name}」+${added.length} −${cut.length}`
    : `「${b?.name || '—'}」`
  const sensitive = roleForm.value.permissions.filter(k => k.startsWith('field.') || k === 'ai.office.admin').length
  return {
    total: roleForm.value.permissions.length,
    equiv,
    modules: `${coveredModules.value.length} / ${gridRows.value.length}`,
    sensitive,
  }
})

function openCreateRole() {
  editingRoleKey.value = null
  roleForm.value = { role_key: '', name: '', description: '', permissions: [] }
  baseKey.value = 'blank'
  awaitingBase.value = true
  roleTab.value = 'perms'
  editorView.value = 'list'
  roleDrawer.value = true
}

function copyRole(role: RoleItem) {
  editingRoleKey.value = null
  roleForm.value = {
    role_key: '',
    name: role.name + '副本',
    description: role.description || '',
    permissions: [...role.permissions],
  }
  baseKey.value = isBuiltin(role.role_key) ? role.role_key : autoBaseFor(role.permissions)
  awaitingBase.value = false
  roleTab.value = 'perms'
  editorView.value = 'list'
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
  baseKey.value = autoBaseFor(role.permissions)
  awaitingBase.value = false
  roleTab.value = 'perms'
  roleDrawer.value = true
}

function openRoleMembers(role: RoleItem) {
  openEditRole(role)
  roleTab.value = 'members'
}

function onRoleMenu(key: string, role: RoleItem) {
  if (key === 'edit') openEditRole(role)
  else if (key === 'members') openRoleMembers(role)
  else if (key === 'copy') copyRole(role)
  else if (key === 'delete') {
    Modal.confirm({
      title: `删除角色「${role.name}」？`,
      content: memberCount(role.role_key)
        ? `该角色仍有 ${memberCount(role.role_key)} 名用户使用，请先在用户管理中改绑角色。`
        : '删除后不可恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => onDeleteRole(role),
    })
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

// ── 用户 ──
const users = ref<AdminUser[]>([])
const usersLoading = ref(false)
const userModal = ref(false)
const userSaving = ref(false)
const userForm = ref<{ name: string; password: string; role: string; email?: string; wecom_userid?: string }>({
  name: '', password: '', role: 'business', email: '', wecom_userid: '',
})
const resetPwdModal = ref(false)
const resetPwd = ref('')
const resetTarget = ref<AdminUser | null>(null)
const userDrawer = ref(false)
const detailUser = ref<AdminUser | null>(null)
const userFilter = ref<'all' | 'on' | 'off'>('all')
const userSearch = ref('')

const userColumns = [
  { title: '用户', key: 'user', sorter: (a: AdminUser, b: AdminUser) => (a.name || '').localeCompare(b.name || '', 'zh') },
  { title: '角色', key: 'role', width: 180 },
  { title: '最近活跃', key: 'last_active', width: 140, sorter: (a: AdminUser, b: AdminUser) => (a.last_login_at || '').localeCompare(b.last_login_at || '') },
  { title: '状态', key: 'active', width: 90 },
  { title: '', key: 'op', width: 56 },
]

// 65+ 账号不全量平铺：20/页，筛选/搜索后不足一页时自动隐藏页码
const userPagination = { pageSize: 20, hideOnSinglePage: true, size: 'small' as const }

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  return users.value.filter(u => {
    if (userFilter.value === 'on' && u.is_active === false) return false
    if (userFilter.value === 'off' && u.is_active !== false) return false
    if (!q) return true
    return (u.name || '').toLowerCase().includes(q) || (u.wecom_userid || '').toLowerCase().includes(q)
  })
})

const rolePickOptions = computed(() =>
  roles.value
    .filter(r => r.role_key !== 'admin')
    .map(r => ({ value: r.role_key, label: `${r.name}${r.description ? ' —— ' + r.description : ''}` })))

function userRowProps(record: AdminUser) {
  return {
    style: { cursor: 'pointer' },
    onClick: () => {
      detailUser.value = record
      userDrawer.value = true
    },
  }
}

function roleRowProps(record: RoleItem) {
  return {
    style: { cursor: 'pointer' },
    onClick: () => openEditRole(record),
  }
}

function lastActiveText(u: AdminUser): string {
  return u.last_login_at ? formatRelativeTime(u.last_login_at) : '—'
}

function isStale(u: AdminUser): boolean {
  if (!u.is_active) return true
  if (!u.last_login_at) return true
  const diff = Date.now() - new Date(u.last_login_at).getTime()
  return Number.isNaN(diff) ? true : diff > 30 * 24 * 3600 * 1000
}

async function loadUsers() {
  usersLoading.value = true
  try {
    users.value = await rbacApi.users.list()
    if (detailUser.value) {
      detailUser.value = users.value.find(u => u.user_id === detailUser.value?.user_id) || null
      if (!detailUser.value) userDrawer.value = false
    }
  } catch {
    message.error('加载用户失败')
  } finally {
    usersLoading.value = false
  }
}

function openCreateUser() {
  userForm.value = { name: '', password: '', role: 'business', email: '', wecom_userid: '' }
  userModal.value = true
}

async function saveUser() {
  if (!userForm.value.name.trim() || userForm.value.password.length < 6) {
    message.warning('用户名不能为空，密码至少 6 位')
    return
  }
  userSaving.value = true
  try {
    const u = await rbacApi.users.create({ ...userForm.value, name: userForm.value.name.trim() })
    if (userForm.value.wecom_userid?.trim()) {
      await rbacApi.users.update(u.user_id, { wecom_userid: userForm.value.wecom_userid.trim() })
    }
    message.success('用户已创建')
    userModal.value = false
    await loadUsers()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '创建失败')
  } finally {
    userSaving.value = false
  }
}

function onUserMenu(key: string, record: AdminUser) {
  if (key === 'detail') {
    detailUser.value = record
    userDrawer.value = true
  } else if (key === 'reset') {
    openResetPwd(record)
  } else if (key === 'toggle') {
    onActiveChange(record, record.is_active === false)
  } else if (key === 'delete') {
    openDeleteUser(record)
  }
}

async function onRoleChange(user: AdminUser, role: string) {
  try {
    await rbacApi.users.update(user.user_id, { role })
    user.role = role
    message.success('角色已更新')
    await loadUsers()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '更新失败')
    await loadUsers()
  }
}

async function onActiveChange(user: AdminUser, active: boolean) {
  try {
    await rbacApi.users.update(user.user_id, { is_active: active })
    user.is_active = active
    message.success(active ? '已启用' : '已停用')
    await loadUsers()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '更新失败')
    await loadUsers()
  }
}

async function onWecomSave(user: AdminUser, value: string) {
  const next = value.trim()
  if ((user.wecom_userid || '') === next) return
  try {
    await rbacApi.users.update(user.user_id, { wecom_userid: next })
    user.wecom_userid = next
    message.success('企微ID已保存')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
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

// ── 角色成员（角色抽屉成员 tab）──
const addMemberOpen = ref(false)
const addMemberSearch = ref('')

function openAddMember() {
  addMemberSearch.value = ''
  addMemberOpen.value = true
}

const roleMembers = computed(() =>
  users.value.filter(u => editingRoleKey.value && (u.role || 'member') === editingRoleKey.value))

const addMemberCandidates = computed(() => {
  const q = addMemberSearch.value.trim().toLowerCase()
  return users.value.filter(u =>
    u.is_active !== false
    && !(editingRoleKey.value && (u.role || 'member') === editingRoleKey.value)
    && (!q || (u.name || '').toLowerCase().includes(q)))
})

async function addRoleMember(u: AdminUser) {
  if (!editingRoleKey.value) return
  try {
    await rbacApi.users.update(u.user_id, { role: editingRoleKey.value })
    message.success(`已将 ${u.name} 加入角色`)
    addMemberOpen.value = false
    await loadUsers()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '添加失败')
  }
}

async function removeRoleMember(u: AdminUser) {
  try {
    await rbacApi.users.update(u.user_id, { role: 'member' })
    message.success(`已将 ${u.name} 移出角色（转为未分配）`)
    await loadUsers()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '移除失败')
  }
}

// ── 删除用户（先转接功能性引用，再删号）──
const deleteModal = ref(false)
const deleteLoading = ref(false)
const deleteUser = ref<AdminUser | null>(null)
const deleteRefs = ref<{ functional: Record<string, number>; historical: Record<string, number> } | null>(null)
const deleteTransferTo = ref<string | undefined>(undefined)

const functionalCount = computed(() =>
  Object.values(deleteRefs.value?.functional || {}).reduce((a, b) => a + b, 0))

const transferOptions = computed(() =>
  users.value
    .filter(u => u.is_active && u.user_id !== deleteUser.value?.user_id)
    .map(u => ({ value: u.user_id, label: `${u.name}（${u.role_name || u.role}）` })))

const REF_LABELS: Record<string, string> = {
  'opportunities.opportunities.owner_user_id': '商机归属',
  'opportunities.opportunities.sales_person': '商机销售人员',
  'opportunities.notifications.user_id': '通知收件',
  'rules.colleague_memories.user_id': '公共域记忆归属',
  'opportunities.opportunity_flows.assignees': '流程指派',
  'opportunities.opportunity_attachments.uploader_user_id': '附件上传',
  'rules.llm_trace.user_id': '模型调用日志',
  'opportunities.opportunity_requirements.created_by': '需求单创建',
  'opportunities.opportunity_bom_schemes.created_by': '方案创建',
  'opportunities.opportunity_cost_sheets.created_by': '成本单创建',
  'opportunities.opportunity_flow_cards.created_by': '流转卡创建',
}

function refLabel(key: string) {
  return REF_LABELS[key] || key
}

async function openDeleteUser(user: AdminUser) {
  deleteUser.value = user
  deleteRefs.value = null
  deleteTransferTo.value = undefined
  deleteModal.value = true
  try {
    const res = await rbacApi.users.references(user.user_id)
    // 弹窗打开期间引用可能已被别人处理，仅当目标未变时采纳结果
    if (deleteUser.value?.user_id === user.user_id) deleteRefs.value = res.references
  } catch {
    deleteRefs.value = { functional: {}, historical: {} }
  }
}

async function confirmDeleteUser() {
  if (!deleteUser.value) return
  if (functionalCount.value > 0 && !deleteTransferTo.value) {
    message.warning('请先选择转接人')
    return
  }
  deleteLoading.value = true
  try {
    const res = await rbacApi.users.remove(deleteUser.value.user_id, deleteTransferTo.value)
    const moved = Object.values(res.transferred || {}).reduce((a, b) => a + b, 0)
    message.success(`已删除 ${deleteUser.value.name}` + (moved ? `，${moved} 条引用已转接` : '（无引用）'))
    deleteModal.value = false
    userDrawer.value = false
    await loadUsers()
  } catch (e: any) {
    const d = e?.response?.data?.detail
    message.error(typeof d === 'string' ? d : (d?.message || '删除失败'))
  } finally {
    deleteLoading.value = false
  }
}

onMounted(async () => {
  try {
    catalog.value = await rbacApi.permissions.list()
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
.urm-sub { font-size: 12px; color: var(--cpq-text-muted, #86909c); }

/* 页级 tab（玻璃分段） */
.page-tabs { display: inline-flex; gap: 4px; padding: 5px; border-radius: var(--cpq-radius-md, 12px); margin-bottom: 14px; }
.page-tab {
  padding: 7px 18px; border-radius: var(--cpq-radius-sm, 8px); cursor: pointer; font-weight: 600;
  color: var(--cpq-text-secondary, #4e5969); font-size: 13px; border: 1px solid transparent;
  transition: all var(--cpq-dur-1, 160ms) var(--cpq-ease-out-expo, ease);
  user-select: none;
}
.page-tab:hover { color: var(--cpq-accent-primary, #1677ff); }
.page-tab.active { color: var(--cpq-accent-primary, #1677ff); background: var(--cpq-overlay-a5, rgba(22,119,255,.05)); border-color: var(--cpq-border-primary, rgba(22,119,255,.1)); }
.page-tab .cnt { font-size: 12px; color: var(--cpq-text-muted, #86909c); font-weight: 400; margin-left: 4px; }

.pane { padding-bottom: 4px; }

/* 工具行 */
.toolbar { display: flex; align-items: center; gap: 12px; padding: 14px 16px 10px; flex-wrap: wrap; }
.toolbar .spacer { flex: 1; }
.hint-text { font-size: 13px; color: var(--cpq-text-muted, #86909c); }
.seg { display: flex; background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); border-radius: var(--cpq-radius-sm, 8px); padding: 3px; gap: 2px; }
.seg-item {
  padding: 4px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; color: var(--cpq-text-secondary, #4e5969);
  transition: all var(--cpq-dur-1, 160ms) var(--cpq-ease-out-expo, ease); user-select: none;
}
.seg-item.active {
  background: var(--cpq-bg-card, #fff); color: var(--cpq-accent-primary, #1677ff); font-weight: 600;
  box-shadow: 0 1px 4px var(--cpq-shadow-color-soft, rgba(22,119,255,.08));
}
.search-box {
  flex: 0 1 260px; display: flex; align-items: center; gap: 8px; padding: 6px 12px;
  border: 1px solid var(--cpq-border-light, rgba(22,119,255,.16)); border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-bg-input, #fff);
}
.search-box input { border: none; outline: none; background: transparent; flex: 1; color: var(--cpq-text-primary, #1d2129); font-size: 13px; }
.cta-btn { box-shadow: 0 4px 12px var(--cpq-shadow-color-soft, rgba(22,119,255,.08)); }

/* 表格单元 */
.cell-user { display: flex; align-items: center; gap: 10px; }
.u-name { font-weight: 600; }
.u-name.lg { font-size: 15px; }
.u-sub { font-size: 11px; color: var(--cpq-text-muted, #86909c); margin-top: 1px; }
.avatar {
  width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: #fff; flex-shrink: 0;
}
.avatar.lg { width: 42px; height: 42px; font-size: 17px; }
.stale { color: var(--cpq-text-disabled, #c9cdd4); }

/* 徽标 */
.badge {
  display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px;
  font-size: 12px; white-space: nowrap; border: 1px solid transparent; line-height: 18px;
}
.badge .dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.badge.role-badge { background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); border-color: var(--cpq-border-primary, rgba(22,119,255,.1)); color: var(--cpq-text-secondary, #4e5969); }
.badge.role-admin { color: var(--cpq-color-purple, #a855f7); background: var(--cpq-overlay-b15, rgba(140,113,255,.12)); border-color: transparent; }
.badge.builtin { color: var(--cpq-text-muted, #86909c); background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); }
.badge.on { color: var(--cpq-color-success, #52C9A0); background: var(--cpq-overlay-success15, rgba(82,201,160,.15)); border-color: transparent; }
.badge.off { color: var(--cpq-text-muted, #86909c); background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); border-color: var(--cpq-border-primary, rgba(22,119,255,.1)); }

/* ⋯ 按钮 */
.op-btn {
  width: 28px; height: 28px; border-radius: 6px; border: none; background: transparent;
  color: var(--cpq-text-muted, #86909c); font-size: 16px; cursor: pointer; line-height: 1;
}
.op-btn:hover { background: var(--cpq-overlay-a8, rgba(22,119,255,.08)); color: var(--cpq-accent-primary, #1677ff); }

/* 角色表 */
.role-name { font-weight: 600; }
.role-desc { font-size: 12px; color: var(--cpq-text-muted, #86909c); margin-top: 2px; }
.link-num { color: var(--cpq-accent-primary, #1677ff); cursor: pointer; font-weight: 600; }
.link-num:hover { text-decoration: underline; }
.perm-dots { display: inline-flex; gap: 3px; vertical-align: middle; }
.perm-dots i { width: 5px; height: 5px; border-radius: 50%; background: var(--cpq-accent-primary, #1677ff); opacity: 0.5; }
.perm-count { font-size: 12px; color: var(--cpq-text-muted, #86909c); }

/* 抽屉 */
.drawer-user-head { display: flex; align-items: center; gap: 12px; }
.drawer-sec { padding: 14px 0 4px; }
.drawer-sec h4 { font-size: 12px; color: var(--cpq-text-muted, #86909c); font-weight: 600; letter-spacing: 0.5px; margin-bottom: 10px; }
.kv { display: grid; grid-template-columns: 88px 1fr; gap: 10px 16px; font-size: 13px; margin: 0; }
.kv dt { color: var(--cpq-text-muted, #86909c); }
.kv dd { margin: 0; color: var(--cpq-text-primary, #1d2129); }
.role-hint { font-size: 12px; color: var(--cpq-text-muted, #86909c); margin-top: 6px; }
.admin-note {
  padding: 10px 14px; border-radius: var(--cpq-radius-sm, 8px); background: var(--cpq-overlay-a4, rgba(22,119,255,.04));
  border: 1px dashed var(--cpq-border-light, rgba(22,119,255,.16)); font-size: 13px; color: var(--cpq-text-secondary, #4e5969);
}

/* Danger Zone */
.danger-zone {
  margin-top: 20px; border: 1px solid var(--cpq-accent-danger, #e5484d); border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-overlay-danger10, rgba(255,107,107,.10)); padding: 14px 16px;
}
.danger-zone h4 { color: var(--cpq-accent-danger, #e5484d); font-size: 13px; margin: 0 0 4px; }
.danger-zone p { font-size: 12px; color: var(--cpq-text-secondary, #4e5969); margin-bottom: 10px; }

/* 角色抽屉 tabs */
.drawer-tabs { display: flex; gap: 20px; border-bottom: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1)); margin-bottom: 4px; }
.drawer-tab {
  padding: 10px 2px; font-size: 14px; color: var(--cpq-text-secondary, #4e5969); cursor: pointer;
  border-bottom: 2px solid transparent; font-weight: 500; user-select: none;
}
.drawer-tab.active { color: var(--cpq-accent-primary, #1677ff); border-bottom-color: var(--cpq-accent-primary, #1677ff); font-weight: 600; }

/* 权限编辑器 */
.perm-summary {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 14px;
  border-radius: var(--cpq-radius-sm, 8px); background: var(--cpq-overlay-a4, rgba(22,119,255,.04));
  border: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1)); font-size: 13px;
  color: var(--cpq-accent-primary, #1677ff); font-weight: 600;
}
.perm-summary .muted { color: var(--cpq-text-muted, #86909c); font-weight: 400; }
.perm-cat { margin-bottom: 6px; }
.perm-cat-title { font-size: 12px; font-weight: 700; color: var(--cpq-text-muted, #86909c); margin: 12px 0 8px; letter-spacing: 0.5px; }
.perm-group { border: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1)); border-radius: var(--cpq-radius-md, 12px); margin-bottom: 10px; overflow: hidden; }
.perm-group-head {
  display: flex; align-items: center; gap: 10px; padding: 9px 14px; font-size: 13px; font-weight: 600;
  background: var(--cpq-overlay-a4, rgba(22,119,255,.04));
}
.perm-group-head .cnt { color: var(--cpq-text-muted, #86909c); font-weight: 400; font-size: 12px; }
.perm-group-head .chk {
  margin-left: auto; display: flex; align-items: center; gap: 5px; font-size: 12px;
  color: var(--cpq-text-muted, #86909c); font-weight: 400; cursor: pointer;
}
.perm-group-head .chk input { accent-color: var(--cpq-accent-primary, #1677ff); }
.perm-items { padding: 4px 14px 10px; }
.perm-item { display: flex; align-items: flex-start; gap: 10px; padding: 6px 4px; cursor: pointer; border-radius: 6px; }
.perm-item:hover { background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); }
.perm-item input { margin-top: 3px; accent-color: var(--cpq-accent-primary, #1677ff); }
.perm-item .label { font-size: 13px; }
.perm-item .key { font-size: 11px; color: var(--cpq-text-disabled, #c9cdd4); font-family: ui-monospace, Consolas, monospace; margin-top: 1px; }
.perm-empty { text-align: center; color: var(--cpq-text-muted, #86909c); font-size: 12px; padding: 12px 0; }

/* 成员行 */
.member-row { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-bottom: 1px solid var(--cpq-border-secondary, rgba(22,119,255,.06)); font-size: 13px; }
.member-row:last-of-type { border-bottom: none; }
.member-row .grow { flex: 1; }
.member-row .mut { color: var(--cpq-text-muted, #86909c); font-size: 12px; }

.reset-tip { color: var(--cpq-text-secondary, #4e5969); margin: 0 0 8px; }
.ref-list { margin: 4px 0; padding-left: 18px; }
.ref-list.muted { color: var(--cpq-text-muted, #86909c); }

/* ══ 角色编辑器 V2（底版+增量 / 网格视图）══ */
.role-ed-layout { display: flex; gap: 18px; align-items: flex-start; }
.role-ed-main { flex: 1; min-width: 0; }
.role-ed-side {
  width: 264px; flex-shrink: 0; border-left: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1));
  padding-left: 16px;
}
.role-ed-side h4 { font-size: 12px; color: var(--cpq-text-muted, #86909c); font-weight: 700; letter-spacing: 0.5px; margin: 0 0 10px; }

/* 步骤条 */
.steps { display: flex; gap: 8px; margin-bottom: 12px; }
.step {
  display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--cpq-text-muted, #86909c);
  padding: 4px 12px; border-radius: 999px; border: 1px dashed var(--cpq-border-light, rgba(22,119,255,.16));
}
.step .n {
  width: 16px; height: 16px; border-radius: 50%; background: var(--cpq-overlay-a8, rgba(22,119,255,.08));
  display: flex; align-items: center; justify-content: center; font-size: 11px;
}
.step.done { color: var(--cpq-color-success, #52C9A0); border-color: var(--cpq-color-success, #52C9A0); border-style: solid; }
.step.done .n { background: var(--cpq-color-success, #52C9A0); color: #fff; }
.step.cur { color: var(--cpq-accent-primary, #1677ff); border-color: var(--cpq-accent-primary, #1677ff); border-style: solid; font-weight: 600; }
.step.cur .n { background: var(--cpq-accent-primary, #1677ff); color: #fff; }

/* 底版卡 */
.base-title { font-size: 13px; font-weight: 700; color: var(--cpq-text-muted, #86909c); letter-spacing: 0.5px; margin-bottom: 10px; }
.base-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.base-card {
  border: 1px solid var(--cpq-border-light, rgba(22,119,255,.16)); border-radius: var(--cpq-radius-md, 12px);
  padding: 11px 13px; cursor: pointer; background: var(--cpq-bg-input, #fff);
  transition: all var(--cpq-dur-1, 160ms) var(--cpq-ease-out-expo, ease);
}
.base-card:hover { border-color: var(--cpq-accent-primary, #1677ff); transform: translateY(-1px); box-shadow: 0 6px 16px var(--cpq-shadow-color-soft, rgba(22,119,255,.08)); }
.base-card.sel { border-color: var(--accent); border-color: var(--cpq-accent-primary, #1677ff); box-shadow: 0 0 0 2px var(--cpq-overlay-a10, rgba(22,119,255,.10)); }
.base-card .nm { font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 6px; }
.base-card .nm .dot { width: 7px; height: 7px; border-radius: 50%; }
.base-card .ds { font-size: 11px; color: var(--cpq-text-muted, #86909c); margin-top: 4px; line-height: 1.5; min-height: 32px; }
.base-card .ct { font-size: 11px; color: var(--cpq-accent-primary, #1677ff); margin-top: 6px; font-weight: 600; }

/* Diff 条 + chips */
.diff-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 9px 14px; margin-bottom: 8px;
  border-radius: var(--cpq-radius-sm, 8px); background: var(--cpq-overlay-a4, rgba(22,119,255,.04));
  border: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1)); font-size: 13px;
}
.diff-bar b { color: var(--cpq-accent-primary, #1677ff); }
.diff-bar .base-name { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; }
.diff-bar .base-name .dot { width: 7px; height: 7px; border-radius: 50%; }
.diff-bar .muted { color: var(--cpq-text-muted, #86909c); }
.diff-bar .d-add { color: var(--cpq-color-success, #52C9A0); font-weight: 600; }
.diff-bar .d-cut { color: var(--cpq-accent-danger, #e5484d); font-weight: 600; }
.diff-bar .link { color: var(--cpq-accent-primary, #1677ff); cursor: pointer; font-size: 12px; margin-left: auto; }
.diff-bar .link:hover { text-decoration: underline; }
.diff-chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 0 0 12px; min-height: 24px; }
.dchip {
  display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px;
  font-size: 12px; user-select: none;
}
.dchip.add { color: var(--cpq-color-success, #52C9A0); background: var(--cpq-overlay-success15, rgba(82,201,160,.15)); }
.dchip.cut { color: var(--cpq-accent-danger, #e5484d); background: var(--cpq-overlay-danger10, rgba(255,107,107,.10)); }
.dchip.cut .lb, .dchip.cut { text-decoration: line-through; }
.dchip .x { cursor: pointer; opacity: 0.7; font-style: normal; }
.dchip .x:hover { opacity: 1; }
.dchip.none { color: var(--cpq-text-muted, #86909c); background: transparent; border: 1px dashed var(--cpq-border-light, rgba(22,119,255,.16)); }

/* 视图切换 */
.view-toggle { display: flex; gap: 2px; background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); border-radius: var(--cpq-radius-sm, 8px); padding: 3px; margin-bottom: 12px; width: fit-content; }
.vt { padding: 4px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; color: var(--cpq-text-muted, #86909c); user-select: none; }
.vt.active { background: var(--cpq-bg-card, #fff); color: var(--cpq-accent-primary, #1677ff); font-weight: 600; box-shadow: 0 1px 4px var(--cpq-shadow-color-soft, rgba(22,119,255,.08)); }

/* 权限状态徽标 */
.tag { display: inline-block; font-size: 10px; padding: 0 6px; border-radius: 999px; margin-left: 6px; vertical-align: 1px; }
.tag.base { color: var(--cpq-text-muted, #86909c); background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); border: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1)); }
.tag.add { color: var(--cpq-color-success, #52C9A0); background: var(--cpq-overlay-success15, rgba(82,201,160,.15)); }
.perm-item.cut .label { text-decoration: line-through; color: var(--cpq-text-muted, #86909c); }

/* 网格视图 */
.grid-wrap { overflow-x: auto; border: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1)); border-radius: var(--cpq-radius-md, 12px); }
table.grid { border-collapse: collapse; width: 100%; }
table.grid th, table.grid td { border-bottom: 1px solid var(--cpq-border-secondary, rgba(22,119,255,.06)); border-right: 1px solid var(--cpq-border-secondary, rgba(22,119,255,.06)); padding: 7px 10px; font-size: 12px; text-align: left; vertical-align: top; }
table.grid thead th { background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); color: var(--cpq-text-muted, #86909c); font-weight: 700; white-space: nowrap; }
table.grid tbody th { background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); font-weight: 600; white-space: nowrap; color: var(--cpq-text-secondary, #4e5969); }
table.grid tr:last-child td, table.grid tr:last-child th { border-bottom: none; }
table.grid td:last-child, table.grid th:last-child { border-right: none; }
.gitem { display: flex; align-items: flex-start; gap: 6px; padding: 2px 0; }
.gitem input { margin-top: 2px; accent-color: var(--cpq-accent-primary, #1677ff); }
.gitem .lb { font-size: 12px; line-height: 1.4; }
.gitem.cut .lb { text-decoration: line-through; color: var(--cpq-text-muted, #86909c); }
.gcell-none { color: var(--cpq-text-disabled, #c9cdd4); font-size: 11px; }

/* 侧栏 */
.form-item { margin-bottom: 10px; }
.form-item label { display: block; font-size: 12px; color: var(--cpq-text-muted, #86909c); margin-bottom: 5px; }
.preview-card { border: 1px solid var(--cpq-border-primary, rgba(22,119,255,.1)); border-radius: var(--cpq-radius-md, 12px); padding: 10px 14px; background: var(--cpq-overlay-a4, rgba(22,119,255,.04)); }
.preview-card .row { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; }
.preview-card .row .v { font-weight: 700; color: var(--cpq-accent-primary, #1677ff); }
.side-note { font-size: 11px; color: var(--cpq-text-muted, #86909c); line-height: 1.7; margin-top: 12px; }
</style>
