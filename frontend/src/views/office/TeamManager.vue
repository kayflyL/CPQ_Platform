<template>
  <div class="tm-root">
    <header v-if="!embedded" class="tm-header">
      <div class="tm-heading">
        <SettingOutlined />
        <h2>Manage Teams</h2>
      </div>

      <a-radio-group v-model:value="editorTab" button-style="solid" size="small" class="tm-editor-tabs">
        <a-radio-button value="team">团队</a-radio-button>
        <a-radio-button value="space">空间</a-radio-button>
        <a-radio-button value="behavior">行为</a-radio-button>
        <a-radio-button value="character">员工</a-radio-button>
      </a-radio-group>

      <div class="tm-actions">
        <template v-if="editorTab === 'team'">
          <a-button v-if="mode === 'view'" @click="mode = 'edit'">
            <template #icon><EditOutlined /></template>
            编辑团队
          </a-button>
          <a-button v-else @click="mode = 'view'">
            取消编辑
          </a-button>
        </template>
        <a-button type="primary" :loading="savingTab" @click="handleHeaderSave">
          <template #icon><SaveOutlined /></template>
          {{ headerSaveText }}
        </a-button>
        <a-button type="text" aria-label="关闭" @click="$emit('close')">
          <template #icon><CloseOutlined /></template>
        </a-button>
      </div>
    </header>

    <div class="tm-body">
      <div v-if="editorTab === 'team'" class="tm-team-panes">
      <!-- Left: selected colleague config -->
      <aside class="tm-left">
        <div class="tm-panel-title">同事配置</div>

        <template v-if="selectedColleague">
          <div class="tm-agent-summary">
            <div class="tm-agent-avatar" :style="{ background: selectedColleague.color || '#1677ff' }">
              <img v-if="selectedColleague.avatar_url" :src="selectedColleague.avatar_url" alt="" />
              <span v-else>{{ avatarInitial(selectedColleague.name) }}</span>
            </div>
            <div class="tm-agent-copy">
              <div class="tm-agent-name">{{ selectedColleague.name || selectedColleague.role_key }}</div>
              <div class="tm-agent-role">{{ selectedColleague.role_key }}</div>
            </div>
            <a-tag :color="selectedColleague.enabled ? 'success' : 'default'">
              {{ selectedColleague.enabled ? '启用' : '停用' }}
            </a-tag>
          </div>

          <div v-if="mode === 'view'" class="tm-view-fields">
            <div class="tm-field">
              <span class="tm-field-label">工具</span>
              <span class="tm-field-value">
                <template v-if="selectedColleague.tool_ids?.length">
                  {{ selectedColleague.tool_ids.join(' · ') }}
                </template>
                <template v-else>暂无</template>
              </span>
            </div>
            <a-button block @click="mode = 'edit'">
              <template #icon><EditOutlined /></template>
              编辑该同事
            </a-button>
          </div>

          <div v-else class="tm-edit-fields">
            <label class="tm-label">名称</label>
            <a-input v-model:value="draftColleague.name" />

            <label class="tm-label">角色标识</label>
            <a-input :value="selectedColleague.role_key" disabled />

            <label class="tm-label">头像 URL</label>
            <a-input v-model:value="draftColleague.avatar_url" placeholder="https://…，留空显示首字" />

            <label class="tm-label">主题色</label>
            <input v-model="draftColleague.color" type="color" class="tm-color-input" />

            <label class="tm-label">启用</label>
            <a-switch v-model:checked="draftColleague.enabled" />

            <label class="tm-label">开场白</label>
            <a-textarea v-model:value="draftColleague.opening_message" :auto-size="{ minRows: 2, maxRows: 4 }" />

            <label class="tm-label">回复风格</label>
            <a-radio-group v-model:value="draftColleague.response_style">
              <a-radio value="brief">简洁</a-radio>
              <a-radio value="detailed">详细</a-radio>
            </a-radio-group>

            <label class="tm-label">模型覆盖</label>
            <a-input v-model:value="draftColleague.model_override" placeholder="留空使用默认模型" />

            <label class="tm-label">可用工具</label>
            <a-select
              v-model:value="draftColleague.tool_ids"
              mode="multiple"
              :options="toolOptions"
              placeholder="从工具注册表选择"
              style="width: 100%"
            />

            <label class="tm-label">数据来源</label>
            <a-select v-model:value="draftColleague.data_sources" mode="multiple" placeholder="选择数据来源" style="width: 100%">
              <a-select-option v-for="item in scopeOptions.data_sources" :key="item.key" :value="item.key">
                <span :title="item.description">{{ item.key }}</span>
              </a-select-option>
            </a-select>

            <label class="tm-label">权限策略</label>
            <a-select v-model:value="draftColleague.permission_policy" style="width: 100%">
              <a-select-option value="readonly">只读</a-select-option>
              <a-select-option value="confirm_before_write">确认后写入</a-select-option>
            </a-select>

            <label class="tm-label">允许总助分派</label>
            <a-switch v-model:checked="draftColleague.dispatchable" />

          </div>
        </template>

        <div v-if="selectedColleague" class="tm-delete-action">
          <a-button danger block :loading="deletingColleague" @click="confirmDeleteColleague">
            <template #icon><DeleteOutlined /></template>
            删除同事
          </a-button>
        </div>

        <div v-else class="tm-left-empty">
          <UserOutlined />
          <p>点击画布中的节点查看和编辑同事详情</p>
        </div>
              </aside>

      <!-- Center: team flow canvas -->
      <main class="tm-center">
        <div class="tm-flow-wrap">
          <VueFlow
            v-model:nodes="nodes"
            v-model:edges="edges"
            :node-types="nodeTypes"
            :node-origin="[0.5, 0]"
            fit-view-on-init
            :min-zoom="0.4"
            :max-zoom="1.6"
            @node-click="onNodeClick"
            @pane-click="onPaneClick"
            @connect="onConnect"
          >
            <Background :gap="24" :size="1" pattern-color="rgba(127,127,127,0.18)" />
            <Controls />
          </VueFlow>
          <div class="tm-canvas-hint">拖动节点调整团队结构 · 点击节点编辑 · 拖拽连线可建立协作关系</div>
        </div>
      </main>

      <!-- Right: team card / team meta -->
      <aside class="tm-right">
        <div class="tm-panel-title">团队</div>

        <div class="tm-team-card" :style="{ borderColor: draftTeamMeta.color || '#1677ff' }">
          <div class="tm-team-color" :style="{ background: draftTeamMeta.color || '#1677ff' }"></div>
          <div class="tm-team-copy">
            <div class="tm-team-name">{{ draftTeamMeta.name || 'AI 团队' }}</div>
            <div class="tm-team-desc">{{ draftTeamMeta.description || '暂无团队描述' }}</div>
          </div>
          <div class="tm-team-count">{{ managedColleagues.length }} 位同事</div>
        </div>

        <div class="tm-lead-field">
          <span class="tm-lead-label">团队负责人 Lead</span>
          <a-select
            v-if="mode === 'edit'"
            v-model:value="draftLeadRoleKey"
            size="small"
            class="tm-lead-select"
            :options="colleagueOptions"
            placeholder="选择 Lead"
            allow-clear
            @change="onLeadChange"
          />
          <span v-else class="tm-lead-value">{{ leadName }}</span>
        </div>

        <div class="tm-member-actions">
          <a-button size="small" type="dashed" @click="openEmployeeCreate">
            <template #icon><PlusOutlined /></template>
            新增同事
          </a-button>
          <a-button size="small" danger :disabled="!selectedColleague" @click="confirmDeleteColleague">
            <template #icon><DeleteOutlined /></template>
            删除同事
          </a-button>
        </div>

        <div class="tm-members">
          <div v-for="colleague in managedColleagues" :key="colleague.role_key" class="tm-member" @click="selectColleague(colleague.role_key)">
            <span class="tm-member-dot" :style="{ background: colleague.color || '#1677ff' }"></span>
            <span class="tm-member-name">{{ colleague.name || colleague.role_key }}</span>
            <span class="tm-member-role">{{ colleague.role_key }}</span>
          </div>
        </div>

        <div class="tm-panel-title tm-room-title">房间</div>
        <div class="tm-rooms">
          <div v-for="room in draftRooms" :key="room.id" class="tm-room" @click="editRoom(room)">
            <span class="tm-room-dot" :style="{ background: room.color || '#1677ff' }"></span>
            <div class="tm-room-copy">
              <div class="tm-room-name">{{ room.name || room.id }}</div>
              <div class="tm-room-meta">{{ roomMemberCount(room) }} 位同事{{ room.role_keys?.length ? ' · 已分配' : ' · 全部同事' }}</div>
            </div>
            <EditOutlined class="tm-room-edit" />
          </div>
          <a-button block type="dashed" size="small" @click="openCreateRoom">
            <template #icon><PlusOutlined /></template>
            新增房间
          </a-button>
        </div>

        <a-collapse ghost class="tm-access-collapse">
          <a-collapse-panel key="access" header="AI 角色访问权限">
            <div v-if="mode === 'edit'" class="tm-access-card">
              <div class="tm-access-help">
                开启团队隔离后，只有下面映射到的 AI 角色会出现在该角色的门户、浮动窗和 AI 办公室中；
                关闭后所有人可访问全部 AI 角色。
              </div>
              <div class="tm-access-line">
                <span>启用团队隔离</span>
                <a-switch v-model:checked="draftAccessPolicy.enabled" size="small" />
              </div>

              <label class="tm-label">角色 → AI 角色</label>
              <div v-for="(row, index) in roleAccessRows" :key="`role-access-${index}`" class="tm-policy-row tm-policy-role-row">
                <a-select
                  v-model:value="row.role_key"
                  size="small"
                  :options="roleOptions"
                  placeholder="选择系统角色"
                  show-search
                />
                <a-select
                  v-model:value="row.colleague_keys"
                  mode="multiple"
                  size="small"
                  class="tm-access-select"
                  :options="colleagueOptions"
                  placeholder="选择 AI 角色"
                  allow-clear
                />
                <a-button type="text" size="small" danger @click="removeRoleAccessRow(index)">删除</a-button>
              </div>
              <a-button block size="small" type="dashed" @click="addRoleAccessRow">新增角色规则</a-button>

              <label class="tm-label">未匹配角色默认</label>
              <a-select
                v-model:value="draftAccessPolicy.default_chat_role_keys"
                mode="multiple"
                size="small"
                class="tm-access-select"
                :options="colleagueOptions"
                placeholder="未匹配到角色规则时可访问的 AI 角色"
                allow-clear
              />

              <a-collapse ghost class="tm-user-exceptions">
                <a-collapse-panel key="user" header="用户例外（高级，按需覆盖）">
                  <div v-for="(row, index) in userAccessRows" :key="`user-access-${index}`" class="tm-policy-row tm-policy-user-row">
                    <a-select
                      v-model:value="row.user_key"
                      size="small"
                      class="tm-user-select"
                      :options="userOptions"
                      show-search
                      option-filter-prop="label"
                      placeholder="选择用户"
                    />
                    <a-select
                      v-model:value="row.colleague_keys"
                      mode="multiple"
                      size="small"
                      class="tm-access-select"
                      :options="colleagueOptions"
                      placeholder="选择 AI 角色"
                      allow-clear
                    />
                    <a-button type="text" size="small" danger @click="removeUserAccessRow(index)">删除</a-button>
                  </div>
                  <a-button block size="small" type="dashed" @click="addUserAccessRow">新增用户例外</a-button>
                </a-collapse-panel>
              </a-collapse>
            </div>

            <div v-else class="tm-access-view">
              <span>{{ draftAccessPolicy.enabled ? '团队隔离已启用' : '团队隔离已关闭' }}</span>
              <span>{{ roleAccessRows.length }} 条角色规则 · {{ userAccessRows.length }} 条用户例外</span>
            </div>
          </a-collapse-panel>
        </a-collapse>

        <div v-if="mode === 'edit'" class="tm-team-form">
          <label class="tm-label">团队名称</label>
          <a-input v-model:value="draftTeamMeta.name" />

          <label class="tm-label">团队描述</label>
          <a-textarea v-model:value="draftTeamMeta.description" :auto-size="{ minRows: 3, maxRows: 6 }" />

          <label class="tm-label">团队色</label>
          <input v-model="draftTeamMeta.color" type="color" class="tm-color-input" />

        </div>

        <div v-else class="tm-team-hint">
          点击右上角「编辑团队」可修改团队名称、描述和主题色。
        </div>
        <a-collapse ghost class="tm-access-collapse">
          <a-collapse-panel key="dispatch" header="智能转接规则">
            <div v-if="mode === 'edit'" class="tm-access-card">
              <div class="tm-access-help">
                当用户与总助对话时，若命中关键词或当前入口匹配规则，系统会建议转接给对应专业 AI 同事。
                这里不是门户的“任务调度”，不会直接改变人类任务负责人。
              </div>
              <div class="tm-access-line">
                <span>启用自动转接</span>
                <a-switch v-model:checked="dispatchEnabled" size="small" />
              </div>
              <div v-if="!dispatchRules.length" class="tm-dispatch-empty">暂无转接规则，点击下方按钮新增。</div>
              <div v-for="(rule, index) in dispatchRules" :key="`dispatch-${index}`" class="tm-dispatch-rule-card">
                <div class="tm-dispatch-rule-head">
                  <a-select
                    v-model:value="rule.role_key"
                    :options="colleagueOptions"
                    placeholder="目标 AI 同事"
                    size="small"
                    style="flex: 1"
                  />
                  <a-switch v-model:checked="rule.enabled" size="small" />
                  <a-button type="text" size="small" danger @click="dispatchRules.splice(index, 1)">删除</a-button>
                </div>
                <label class="tm-label">命中关键词</label>
                <a-select
                  v-model:value="rule.keywords"
                  mode="tags"
                  size="small"
                  placeholder="如：报价、成本、选型"
                  style="width: 100%"
                />
                <label class="tm-label">生效入口</label>
                <a-select
                  v-model:value="rule.entry_points"
                  mode="multiple"
                  size="small"
                  :options="pageScopeOptions"
                  placeholder="留空表示所有入口"
                  style="width: 100%"
                  allow-clear
                />
              </div>
              <a-button block size="small" type="dashed" @click="addDispatchRule">新增转接规则</a-button>
            </div>
            <div v-else class="tm-access-view">
              <span>{{ dispatchEnabled ? '自动转接已启用' : '自动转接已关闭' }}</span>
              <span>{{ dispatchRules.length }} 条转接规则</span>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </aside>
      </div>

      <OfficeSpaceEditor ref="spaceEditorRef"
        v-else-if="editorTab === 'space'"
        class="tm-editor-pane"
        :office-config="officeConfig"
        :colleagues="managedColleagues"
        @saved="handleChildSaved"
      />
      <OfficeBehaviorEditor ref="behaviorEditorRef"
        v-else-if="editorTab === 'behavior'"
        class="tm-editor-pane"
        :behavior-config="behaviorConfig"
        :office-config="officeConfig"
        @saved="handleChildSaved"
      />
      <EmployeeManager ref="employeeEditorRef"
        v-else
        class="tm-editor-pane"
        :colleagues="managedColleagues"
        :initial-role-key="initialRoleKey"
        @saved="handleChildSaved"
      />
    </div>

    <a-modal v-model:open="createColleagueOpen" title="新增 AI 同事" :footer="null" width="480">
      <div class="tm-modal-form">
        <label class="tm-label">角色标识</label>
        <a-input v-model:value="createColleagueForm.role_key" placeholder="唯一英文标识，如 data_analyst" />
        <label class="tm-label">名称</label>
        <a-input v-model:value="createColleagueForm.name" placeholder="如 数据分析师" />
        <label class="tm-label">头像 URL</label>
        <a-input v-model:value="createColleagueForm.avatar_url" placeholder="https://…，留空则显示首字" />
        <label class="tm-label">主题色</label>
        <a-input v-model:value="createColleagueForm.color" style="width: 120px" />
        <label class="tm-label">启用</label>
        <a-switch v-model:checked="createColleagueForm.enabled" />
        <label class="tm-label">权限策略</label>
        <a-select v-model:value="createColleagueForm.permission_policy" style="width: 100%">
          <a-select-option value="readonly">只读</a-select-option>
          <a-select-option value="confirm_before_write">确认后写入</a-select-option>
        </a-select>
      </div>
      <div class="tm-modal-actions">
        <a-button @click="createColleagueOpen = false">取消</a-button>
        <a-button type="primary" :loading="creatingColleague" @click="handleCreateColleague">创建</a-button>
      </div>
    </a-modal>

    <a-modal v-model:open="roomModalOpen" :title="roomForm.isEditing ? '编辑房间' : '新增房间'" :footer="null" width="480">
      <div class="tm-modal-form">
        <label class="tm-label">房间标识</label>
        <a-input v-model:value="roomForm.id" :disabled="roomForm.isEditing" placeholder="唯一英文标识，如 quote_team" />
        <label class="tm-label">名称</label>
        <a-input v-model:value="roomForm.name" placeholder="如 报价团队" />
        <label class="tm-label">描述</label>
        <a-textarea v-model:value="roomForm.description" :auto-size="{ minRows: 2, maxRows: 4 }" />
        <label class="tm-label">主题色</label>
        <a-input v-model:value="roomForm.color" style="width: 120px" />
        <label class="tm-label">分配同事</label>
        <a-select v-model:value="roomForm.role_keys" mode="multiple" style="width: 100%" placeholder="留空则包含全部同事">
          <a-select-option v-for="colleague in managedColleagues" :key="colleague.role_key" :value="colleague.role_key">
            {{ colleague.name || colleague.role_key }}
          </a-select-option>
        </a-select>
        <a-button v-if="roomForm.isEditing && draftRooms.length > 1" danger block size="small" @click="deleteRoom(roomForm)">
          删除房间
        </a-button>
      </div>
      <div class="tm-modal-actions">
        <a-button @click="roomModalOpen = false">取消</a-button>
        <a-button type="primary" :loading="savingRooms" @click="saveRoom">保存房间</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, ref, shallowRef, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { VueFlow, type Edge, type Node } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import { CloseOutlined, DeleteOutlined, EditOutlined, PlusOutlined, SaveOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons-vue'
import { officeApi, type BehaviorConfig, type OfficeAccessPolicy, type OfficeConfig } from '@/api/office'
import { assistantApi } from '@/api/assistant'
import OfficeFlowNode from './OfficeFlowNode.vue'
import OfficeSpaceEditor from './OfficeSpaceEditor.vue'
import OfficeBehaviorEditor from './OfficeBehaviorEditor.vue'
import EmployeeManager from './EmployeeManager.vue'

const props = defineProps<{
  colleagues: any[]
  rooms: any[]
  teamMeta: { name?: string; description?: string; color?: string }
  layoutNodes: any[]
  layoutEdges: any[]
  officeConfig?: OfficeConfig
  behaviorConfig?: BehaviorConfig
  accessPolicy?: OfficeAccessPolicy
  initialRoleKey?: string | null
  leadRoleKey?: string | null
  embedded?: boolean
  initialEditorTab?: 'team' | 'space' | 'behavior' | 'character'
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()
const nodes = ref<Node[]>([])
const edges = shallowRef<Edge[]>([])
const nodeTypes = markRaw({ agent: OfficeFlowNode, user: OfficeFlowNode }) as any

const mode = ref<'view' | 'edit'>('view')
const editorTab = ref<'team' | 'space' | 'behavior' | 'character'>(props.initialEditorTab || 'team')
const selectedRoleKey = ref<string | null>(props.initialRoleKey || null)
const draftLeadRoleKey = ref<string | null>(props.leadRoleKey || null)
const leadDirty = ref(false)
const savingTab = ref(false)
const spaceEditorRef = ref<any>(null)
const behaviorEditorRef = ref<any>(null)
const employeeEditorRef = ref<any>(null)
const creatingColleague = ref(false)
const deletingColleague = ref(false)
const savingRooms = ref(false)
const createColleagueOpen = ref(false)
const createColleagueForm = ref({
  role_key: '',
  name: '',
  avatar_url: '',
  color: '#1677ff',
  enabled: true,
  permission_policy: 'readonly',
})
const roomModalOpen = ref(false)
const roomForm = ref<Record<string, any>>({})
const draftRooms = ref<any[]>([])
interface AccessRoleRow { role_key: string; colleague_keys: string[] }
interface AccessUserRow { user_key: string; colleague_keys: string[] }
const roleAccessRows = ref<AccessRoleRow[]>([])
const userAccessRows = ref<AccessUserRow[]>([])
const users = ref<any[]>([])
const roles = ref<Array<{ role_key: string; name: string }>>([])
const adminConfig = ref<any>(null)
const managedColleagues = computed<any[]>(() =>
  Array.isArray(adminConfig.value?.colleagues) && adminConfig.value.colleagues.length
    ? adminConfig.value.colleagues
    : props.colleagues,
)

const draftAccessPolicy = ref<OfficeAccessPolicy>({
  enabled: props.accessPolicy?.enabled ?? true,
  default_room_ids: Array.isArray(props.accessPolicy?.default_room_ids) ? [...props.accessPolicy.default_room_ids] : ['default'],
  role_room_map: { ...(props.accessPolicy?.role_room_map || {}) },
  user_room_map: { ...(props.accessPolicy?.user_room_map || {}) },
  default_chat_role_keys: Array.isArray(props.accessPolicy?.default_chat_role_keys) ? [...props.accessPolicy.default_chat_role_keys] : ['assistant'],
  role_chat_role_keys: { ...(props.accessPolicy?.role_chat_role_keys || {}) },
  user_chat_role_keys: { ...(props.accessPolicy?.user_chat_role_keys || {}) },
})

const draftTeamMeta = ref({
  name: props.teamMeta?.name || 'AI 团队',
  description: props.teamMeta?.description || '',
  color: props.teamMeta?.color || '#1677ff',
})

const draftColleague = ref<Record<string, any>>({})
const toolIdsText = ref('')
const tools = ref<any[]>([])
const dispatchEnabled = ref(true)
const dispatchRules = ref<any[]>([])

const selectedColleague = computed(() =>
  managedColleagues.value.find((c) => c.role_key === selectedRoleKey.value) || null,
)
const roleOptions = computed(() => roles.value.map((role) => ({ value: role.role_key, label: role.name || role.role_key })))
const colleagueOptions = computed(() =>
  managedColleagues.value.map((colleague) => ({
    value: colleague.role_key,
    label: `${colleague.name || colleague.role_key} (${colleague.role_key})`,
  })),
)
const toolOptions = computed(() => tools.value.map((tool) => ({ value: tool.name, label: tool.name })))
const headerSaveText = computed(() => {
  if (editorTab.value === 'space') return '保存空间'
  if (editorTab.value === 'behavior') return '保存行为'
  if (editorTab.value === 'character') return '保存员工'
  return '保存团队'
})
const scopeOptions = ref<{ data_sources: any[]; page_scopes: any[] }>({ data_sources: [], page_scopes: [] })
const pageScopeOptions = computed(() => scopeOptions.value.page_scopes.map((item) => ({ value: item.key, label: item.label || item.key })))
async function loadScopeOptions() {
  try {
    scopeOptions.value = await officeApi.scopeOptions()
  } catch {
    scopeOptions.value = { data_sources: [], page_scopes: [] }
  }
}
loadScopeOptions()
const leadName = computed(() => {
  const current = managedColleagues.value.find((colleague) => colleague.role_key === draftLeadRoleKey.value)
  return current?.name || draftLeadRoleKey.value || '未设置'
})
const userOptions = computed(() =>
  users.value.map((user) => ({ value: user.user_id, label: `${user.name}${user.role ? ` (${user.role})` : ''}` })),
)

watch(
  selectedColleague,
  (colleague) => {
    if (!colleague) {
      draftColleague.value = {}
      toolIdsText.value = ''
      return
    }
    draftColleague.value = { ...colleague }
    toolIdsText.value = Array.isArray(colleague.tool_ids) ? colleague.tool_ids.join(', ') : ''
  },
  { immediate: true },
)

watch(
  () => props.initialRoleKey,
  (roleKey) => {
    if (roleKey) selectedRoleKey.value = roleKey
  },
)

watch(
  () => props.initialEditorTab,
  (tab) => {
    if (tab) editorTab.value = tab
  },
)

watch(
  () => props.rooms,
  (rooms) => {
    if (adminConfig.value) return
    draftRooms.value = (Array.isArray(rooms) ? rooms : []).map((room) => ({
      ...room,
      role_keys: Array.isArray(room.role_keys) ? [...room.role_keys] : [],
    }))
  },
  { immediate: true, deep: true },
)

watch(
  () => props.accessPolicy,
  (policy) => {
    if (adminConfig.value) return
    draftAccessPolicy.value = {
      enabled: policy?.enabled ?? true,
      default_room_ids: Array.isArray(policy?.default_room_ids) ? [...policy.default_room_ids] : ['default'],
      role_room_map: { ...(policy?.role_room_map || {}) },
      user_room_map: { ...(policy?.user_room_map || {}) },
      default_chat_role_keys: Array.isArray(policy?.default_chat_role_keys) ? [...policy.default_chat_role_keys] : ['assistant'],
      role_chat_role_keys: { ...(policy?.role_chat_role_keys || {}) },
      user_chat_role_keys: { ...(policy?.user_chat_role_keys || {}) },
    }
    syncAccessPolicyRows()
  },
  { immediate: true, deep: true },
)

function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

function leadFromEdges(): any | null {
  if (!managedColleagues.value.length) return null
  const defaultLead = managedColleagues.value.find((c) => c.role_key === 'assistant')
  if (defaultLead) return defaultLead
  const leadEdge = (props.layoutEdges || []).find((edge) => edge?.source === 'user' && edge?.target)
  if (leadEdge?.target) {
    const matched = managedColleagues.value.find((c) => c.role_key === leadEdge.target)
    if (matched) return matched
  }
  return managedColleagues.value.find((c) => c.enabled !== false) || managedColleagues.value[0] || null
}

function leadColleague(): any | null {
  if (draftLeadRoleKey.value) {
    return managedColleagues.value.find((c) => c.role_key === draftLeadRoleKey.value) || leadFromEdges()
  }
  return leadFromEdges()
}

function storedPosition(nodeId: string): { x: number; y: number } | null {
  const stored = (props.layoutNodes || []).find((n) => n?.id === nodeId)
  if (stored && typeof stored.position?.x === 'number' && typeof stored.position?.y === 'number') {
    return stored.position
  }
  return null
}

function buildFlow() {
  const userNode: Node = {
    id: 'user',
    type: 'user',
    position: storedPosition('user') || { x: 0, y: 0 },
    data: {
      kind: 'user',
      label: '用户',
      sublabel: 'Human',
      color: '#8b5cf6',
      isRoot: true,
      isLead: false,
      isLeaf: false,
    },
  }

  const flowNodes: Node[] = [userNode]
  const flowEdges: Edge[] = []
  const lead = leadColleague()

  if (lead) {
    flowNodes.push({
      id: lead.role_key,
      type: 'agent',
      position: storedPosition(lead.role_key) || { x: 0, y: 170 },
      data: {
        kind: 'agent',
        label: lead.name || lead.role_key,
        sublabel: lead.role_key,
        color: lead.color || '#1677ff',
        isRoot: false,
        isLead: true,
        isLeaf: managedColleagues.value.length <= 1,
      },
    })

    flowEdges.push({
      id: 'edge-user-lead',
      source: 'user',
      target: lead.role_key,
      type: 'smoothstep',
    })
  }

  const offsets = [0, -300, 300, -600, 600, -900, 900]
  let subIndex = 0
  for (const colleague of managedColleagues.value) {
    if (!lead || colleague.role_key === lead.role_key) continue

    flowNodes.push({
      id: colleague.role_key,
      type: 'agent',
      position: storedPosition(colleague.role_key) || {
        x: offsets[subIndex % offsets.length],
        y: 360,
      },
      data: {
        kind: 'agent',
        label: colleague.name || colleague.role_key,
        sublabel: colleague.role_key,
        color: colleague.color || '#1677ff',
        isRoot: false,
        isLead: false,
        isLeaf: true,
      },
    })

    flowEdges.push({
      id: `edge-lead-${colleague.role_key}`,
      source: lead.role_key,
      target: colleague.role_key,
      type: 'smoothstep',
    })

    subIndex += 1
  }

  const storedEdges = props.layoutEdges || []
  const mergedEdges = [...flowEdges]
  for (const edge of storedEdges) {
    if (lead) {
      if (edge.source === 'user' && edge.target !== lead.role_key) continue
      if (edge.source === lead.role_key || edge.target === lead.role_key) continue
      if ((edge.id || '').startsWith('edge-lead-') && edge.source !== lead.role_key) continue
    }
    if (!mergedEdges.some((e) => e.id === edge.id || (e.source === edge.source && e.target === edge.target))) {
      mergedEdges.push(edge)
    }
  }

  nodes.value = flowNodes
  edges.value = mergedEdges as Edge[]
}

function onNodeClick(event: { node: Node }) {
  if (event.node.id === 'user' || event.node.data?.isLead) {
    selectedRoleKey.value = null
    return
  }
  selectedRoleKey.value = event.node.id
}

function onPaneClick() {
  selectedRoleKey.value = null
}

function onConnect(params: any) {
  if (!params.source || !params.target || params.source === params.target) return
  const exists = edges.value.some(
    (e) => e.source === params.source && e.target === params.target,
  )
  if (exists) return

  edges.value = [
    ...edges.value,
    {
      id: `edge-${params.source}-${params.target}-${Date.now()}`,
      source: params.source,
      target: params.target,
      type: 'smoothstep',
    },
  ] as Edge[]
}

function selectColleague(roleKey: string) {
  selectedRoleKey.value = roleKey
}

function onLeadChange(roleKey?: string | null) {
  leadDirty.value = true
  draftLeadRoleKey.value = roleKey || null
}

function openEmployeeCreate() {
  editorTab.value = 'character'
  selectedRoleKey.value = null
  nextTick(() => employeeEditorRef.value?.openCreate())
}

async function handleCreateColleague() {
  const form = createColleagueForm.value
  const roleKey = (form.role_key || '').trim()
  if (!roleKey) {
    message.warning('请填写角色标识')
    return
  }
  creatingColleague.value = true
  try {
    await officeApi.createColleague({
      role_key: roleKey,
      name: form.name?.trim() || roleKey,
      avatar_url: form.avatar_url || '',
      color: form.color || '#1677ff',
      enabled: form.enabled,
      permission_policy: form.permission_policy || 'readonly',
    })
    message.success(`已新增 ${roleKey}`)
    createColleagueOpen.value = false
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '新增同事失败')
  } finally {
    creatingColleague.value = false
  }
}

function confirmDeleteColleague() {
  const colleague = selectedColleague.value
  if (!colleague) return
  Modal.confirm({
    title: `删除 AI 同事「${colleague.name || colleague.role_key}」？`,
    content: '删除后该同事配置及关联房间分配会一并移除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: handleDeleteColleague,
  })
}

async function handleDeleteColleague() {
  const colleague = selectedColleague.value
  if (!colleague) return
  deletingColleague.value = true
  try {
    await officeApi.deleteColleague(colleague.role_key)
    message.success(`已删除 ${colleague.role_key}`)
    selectedRoleKey.value = null
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '删除同事失败')
  } finally {
    deletingColleague.value = false
  }
}

function roomMemberCount(room: any): number {
  const roleKeys = Array.isArray(room.role_keys) ? room.role_keys : []
  if (!roleKeys.length) return managedColleagues.value.length
  return managedColleagues.value.filter((colleague) => roleKeys.includes(colleague.role_key)).length
}

function openCreateRoom() {
  roomForm.value = {
    id: '',
    name: '',
    description: '',
    color: '#1677ff',
    role_keys: [],
    isEditing: false,
  }
  roomModalOpen.value = true
}

function editRoom(room: any) {
  roomForm.value = {
    ...room,
    role_keys: Array.isArray(room.role_keys) ? [...room.role_keys] : [],
    originalId: room.id,
    isEditing: true,
  }
  roomModalOpen.value = true
}

async function saveRoom() {
  const form = roomForm.value
  const roomId = (form.id || '').trim()
  if (!roomId) {
    message.warning('请填写房间标识')
    return
  }
  if (!form.name?.trim()) {
    message.warning('请填写房间名称')
    return
  }
  const exists = draftRooms.value.some((room) => room.id === roomId && room.id !== form.originalId)
  if (exists) {
    message.warning('房间标识已存在')
    return
  }
  savingRooms.value = true
  try {
    const room = {
      id: roomId,
      name: form.name.trim(),
      description: form.description || '',
      color: form.color || '#1677ff',
      role_keys: Array.isArray(form.role_keys) ? form.role_keys : [],
    }
    const rooms = form.isEditing
      ? draftRooms.value.map((item) => (item.id === form.originalId ? room : item))
      : [...draftRooms.value, room]
    await officeApi.updateRooms({ rooms })
    draftRooms.value = rooms
    message.success('房间已保存')
    roomModalOpen.value = false
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '房间保存失败')
  } finally {
    savingRooms.value = false
  }
}

function deleteRoom(room: any) {
  if (!room?.id) return
  if (draftRooms.value.length <= 1) {
    message.warning('至少保留一个房间')
    return
  }
  Modal.confirm({
    title: `删除房间「${room.name || room.id}」？`,
    content: '删除房间不会删除 AI 同事，只会移除该房间视图。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      savingRooms.value = true
      try {
        const rooms = draftRooms.value.filter((item) => item.id !== room.id)
        await officeApi.updateRooms({ rooms })
        draftRooms.value = rooms
        roomModalOpen.value = false
        message.success('房间已删除')
        emit('saved')
      } catch (error: any) {
        message.error(error?.response?.data?.detail || '房间删除失败')
      } finally {
        savingRooms.value = false
      }
    },
  })
}

function toColleagueKeys(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item) => typeof item === 'string') : []
}

function syncAccessPolicyRows() {
  roleAccessRows.value = Object.entries(draftAccessPolicy.value.role_chat_role_keys || {})
    .map(([role_key, value]) => ({ role_key, colleague_keys: toColleagueKeys(value) }))
  userAccessRows.value = Object.entries(draftAccessPolicy.value.user_chat_role_keys || {})
    .map(([user_key, value]) => ({ user_key, colleague_keys: toColleagueKeys(value) }))
}

function addRoleAccessRow() {
  roleAccessRows.value.push({ role_key: '', colleague_keys: [] })
}

function removeRoleAccessRow(index: number) {
  roleAccessRows.value.splice(index, 1)
}

function addUserAccessRow() {
  userAccessRows.value.push({ user_key: '', colleague_keys: [] })
}

function removeUserAccessRow(index: number) {
  userAccessRows.value.splice(index, 1)
}

async function loadRoles() {
  try {
    const data = await officeApi.teamRoles()
    roles.value = Array.isArray(data.roles) ? data.roles : []
  } catch {
    roles.value = []
  }
}

async function loadAdminConfig() {
  try {
    const data = await officeApi.teamConfigAdmin()
    adminConfig.value = data
    draftRooms.value = (Array.isArray(data.rooms) ? data.rooms : []).map((room: any) => ({
      ...room,
      role_keys: Array.isArray(room.role_keys) ? [...room.role_keys] : [],
    }))
    draftAccessPolicy.value = {
      enabled: data.access_policy?.enabled ?? true,
      default_chat_role_keys: Array.isArray(data.access_policy?.default_chat_role_keys) ? [...data.access_policy.default_chat_role_keys] : ['assistant'],
      role_chat_role_keys: { ...(data.access_policy?.role_chat_role_keys || {}) },
      user_chat_role_keys: { ...(data.access_policy?.user_chat_role_keys || {}) },
    }
    syncAccessPolicyRows()
  } catch {
    adminConfig.value = null
  }
}

async function handleChildSaved() {
  await loadAdminConfig()
  emit('saved')
}

async function loadUsers() {
  try {
    const data = await officeApi.listUsers()
    users.value = Array.isArray(data.users) ? data.users.filter((user) => user.is_active !== false) : []
  } catch {
    users.value = []
  }
}

async function loadTools() {
  try {
    tools.value = await assistantApi.tools.catalog()
  } catch (error) {
    console.error('加载 AI 工具目录失败:', error)
  }
}

async function loadDispatch() {
  try {
    const data = await officeApi.teamConfigAdmin()
    dispatchEnabled.value = data.dispatch_enabled !== false
    dispatchRules.value = (Array.isArray(data.dispatch_rules) ? data.dispatch_rules : []).map((rule: any) => ({
      role_key: rule?.role_key || '',
      keywords: Array.isArray(rule?.keywords) ? rule.keywords : [],
      entry_points: Array.isArray(rule?.entry_points) ? rule.entry_points : [],
      enabled: rule?.enabled !== false,
    }))
  } catch (error) {
    console.error('加载总助分派规则失败:', error)
  }
}

function addDispatchRule() {
  dispatchRules.value.push({ role_key: '', keywords: [], entry_points: [], enabled: true })
}

async function handleHeaderSave() {
  if (savingTab.value) return
  savingTab.value = true
  try {
    if (editorTab.value === 'team') {
      await saveTeamTab()
    } else if (editorTab.value === 'space') {
      const editor = spaceEditorRef.value
      if (!editor || typeof editor.save !== 'function') {
        message.error('空间编辑器保存功能未就绪')
        return
      }
      await editor.save()
    } else if (editorTab.value === 'behavior') {
      const editor = behaviorEditorRef.value
      if (!editor || typeof editor.save !== 'function') {
        message.error('行为编辑器保存功能未就绪')
        return
      }
      await editor.save()
    } else if (editorTab.value === 'character') {
      const editor = employeeEditorRef.value
      if (!editor || typeof editor.save !== 'function') {
        message.error('员工编辑器保存功能未就绪')
        return
      }
      await editor.save()
    }
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '保存失败')
  } finally {
    savingTab.value = false
  }
}

async function saveTeamTab() {
  if (mode.value === 'edit' && selectedColleague.value) {
    const roleKey = selectedColleague.value.role_key
    await officeApi.updateColleague(roleKey, {
      name: draftColleague.value.name,
      avatar_url: draftColleague.value.avatar_url || '',
      color: draftColleague.value.color,
      enabled: draftColleague.value.enabled,
      opening_message: draftColleague.value.opening_message,
      response_style: draftColleague.value.response_style || 'detailed',
      model_override: draftColleague.value.model_override || null,
      tool_ids: Array.isArray(draftColleague.value.tool_ids) ? draftColleague.value.tool_ids : [],
      data_sources: Array.isArray(draftColleague.value.data_sources) ? draftColleague.value.data_sources : [],
      permission_policy: draftColleague.value.permission_policy || 'readonly',
      dispatchable: Boolean(draftColleague.value.dispatchable),
    })
  }

  if (mode.value === 'edit') {
    await officeApi.updateTeamMeta({
      name: draftTeamMeta.value.name,
      description: draftTeamMeta.value.description,
      color: draftTeamMeta.value.color,
    })

    const roleChatRoleKeys: Record<string, string[]> = {}
    for (const row of roleAccessRows.value) {
      const key = row.role_key.trim()
      if (key) roleChatRoleKeys[key] = [...row.colleague_keys]
    }
    const userChatRoleKeys: Record<string, string[]> = {}
    for (const row of userAccessRows.value) {
      const key = row.user_key.trim()
      if (key) userChatRoleKeys[key] = [...row.colleague_keys]
    }
    const accessPayload: OfficeAccessPolicy = {
      enabled: Boolean(draftAccessPolicy.value.enabled),
      default_chat_role_keys: [...(draftAccessPolicy.value.default_chat_role_keys || [])],
      role_chat_role_keys: roleChatRoleKeys,
      user_chat_role_keys: userChatRoleKeys,
    }
    await officeApi.updateAccessPolicy(accessPayload)
    draftAccessPolicy.value = accessPayload

    await officeApi.updateDispatch({
      dispatch_enabled: dispatchEnabled.value,
      dispatch_rules: dispatchRules.value,
    })
  }

  const payloadNodes = (nodes.value as any[]).map((node: any) => ({
    id: node.id,
    type: node.type,
    position: node.position,
    data: node.data,
  }))
  const payloadEdges = edges.value.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: edge.type,
  }))

  await officeApi.updateLayout({
    nodes: payloadNodes,
    edges: payloadEdges,
    lead_role_key: draftLeadRoleKey.value || undefined,
  })
  await loadAdminConfig()
  leadDirty.value = false
  message.success('团队配置已保存')
  emit('saved')
}

onMounted(() => {
  loadUsers()
  loadTools()
  loadRoles()
  loadAdminConfig()
  loadDispatch()
})

watch(
  () => props.leadRoleKey,
  (value) => {
    if (!leadDirty.value) {
      draftLeadRoleKey.value = value || null
    }
  },
)

watch(
  () => [managedColleagues.value, props.layoutNodes, props.layoutEdges],
  () => {
    if (!leadDirty.value) {
      draftLeadRoleKey.value = props.leadRoleKey || leadFromEdges()?.role_key || null
    }
    buildFlow()
  },
  { immediate: true, deep: true },
)

watch(draftLeadRoleKey, () => buildFlow())

defineExpose({ save: handleHeaderSave })
</script>

<style scoped>
.tm-root {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--cpq-bg-primary);
  color: var(--cpq-text-primary);
  overflow: hidden;
}

/* Header */
.tm-header {
  height: 60px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 18px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.04));
}

.tm-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.tm-heading :deep(.anticon) {
  color: var(--cpq-accent-primary, #1677ff);
  font-size: 18px;
}

.tm-heading h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--cpq-text-primary);
}

.tm-subtitle {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.tm-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.tm-editor-tabs {
  flex-shrink: 0;
}

.tm-team-panes {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
}

/* Body: 3-column Manage Teams layout */
.tm-body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.tm-editor-pane {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.tm-left,
.tm-right {
  width: 320px;
  flex-shrink: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.04));
}

.tm-left {
  border-right: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

.tm-right {
  border-left: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

.tm-panel-title {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--cpq-text-muted);
  margin-bottom: 12px;
}

/* Left config */
.tm-agent-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.tm-agent-avatar {
  width: 44px;
  height: 44px;
  border-radius: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
  overflow: hidden;
  flex-shrink: 0;
}

.tm-agent-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tm-agent-copy {
  flex: 1;
  min-width: 0;
}

.tm-agent-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.tm-agent-role {
  margin-top: 2px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  font-family: ui-monospace, monospace;
}

.tm-view-fields,
.tm-edit-fields,
.tm-team-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tm-field {
  padding: 10px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 10px;
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.03));
}

.tm-field-label,
.tm-label {
  display: block;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.tm-field-value {
  display: block;
  font-size: 12px;
  line-height: 1.5;
  color: var(--cpq-text-secondary);
  word-break: break-word;
}

.tm-edit-fields {
  padding-bottom: 8px;
}

.tm-label {
  margin-bottom: 0;
  margin-top: 4px;
}

.tm-color-input {
  width: 100%;
  height: 36px;
  padding: 2px 6px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 8px;
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.03));
  cursor: pointer;
}

.tm-left-empty {
  padding: 40px 20px;
  text-align: center;
  color: var(--cpq-text-muted);
  border: 1px dashed var(--cpq-border-secondary, rgba(255,255,255,0.12));
  border-radius: 14px;
}

.tm-left-empty :deep(.anticon) {
  font-size: 28px;
  opacity: .35;
}

.tm-left-empty p {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

/* Center canvas */
.tm-center {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
  display: flex;
  overflow: hidden;
  background: var(--cpq-bg-primary);
}

.tm-flow-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.tm-flow-wrap :deep(.vue-flow) {
  background: var(--cpq-bg-primary);
}

.tm-canvas-hint {
  position: absolute;
  left: 50%;
  bottom: 12px;
  transform: translateX(-50%);
  z-index: 5;
  pointer-events: none;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  background: color-mix(in srgb, var(--cpq-bg-elevated, #101722) 82%, transparent);
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

/* Right team panel */
.tm-team-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid;
  border-radius: 14px;
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.03));
  margin-bottom: 14px;
}

.tm-team-color {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  flex-shrink: 0;
  box-shadow: 0 0 16px color-mix(in srgb, currentColor 45%, transparent);
}

.tm-team-copy {
  flex: 1;
  min-width: 0;
}

.tm-team-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.tm-team-desc {
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--cpq-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tm-team-count {
  flex-shrink: 0;
  padding: 4px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 800;
  color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w8, rgba(255,255,255,0.08));
}

.tm-lead-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.tm-lead-label {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--cpq-text-secondary);
}

.tm-lead-select {
  flex: 1;
  min-width: 0;
}

.tm-lead-value {
  font-size: 11px;
  color: var(--cpq-text-primary);
}

.tm-members {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 14px;
}

.tm-member {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 9px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 12px;
  transition: background .18s ease;
}

.tm-member:hover {
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
}

.tm-member-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tm-member-name {
  flex: 1;
  min-width: 0;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tm-member-role {
  font-size: 10px;
  color: var(--cpq-text-muted);
  font-family: ui-monospace, monospace;
}

.tm-team-hint {
  font-size: 12px;
  line-height: 1.5;
  color: var(--cpq-text-muted);
}

.tm-delete-action {
  margin-top: 14px;
}

.tm-member-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.tm-member-actions .ant-btn {
  flex: 1;
}

.tm-room-title {
  margin-top: 4px;
}

.tm-rooms {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.tm-room {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 9px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 10px;
  cursor: pointer;
  transition: border-color .18s ease, background .18s ease;
}

.tm-room:hover {
  border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
}

.tm-room-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tm-room-copy {
  flex: 1;
  min-width: 0;
}

.tm-room-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.tm-room-meta {
  margin-top: 2px;
  font-size: 10px;
  color: var(--cpq-text-muted);
}

.tm-room-edit {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.tm-modal-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tm-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}

.tm-access-collapse {
  margin-top: 14px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  background: transparent;
}

.tm-access-collapse :deep(.ant-collapse-header) {
  padding: 10px 12px !important;
  font-size: 12px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.tm-access-collapse :deep(.ant-collapse-content) {
  border-top: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: transparent;
}

.tm-access-collapse :deep(.ant-collapse-content-box) {
  padding: 10px 0 0;
}

@media (max-width: 900px) {
  .tm-header {
    padding: 0 10px;
  }

  .tm-subtitle {
    display: none;
  }

  .tm-left,
  .tm-right {
    width: 250px;
  }
}

@media (max-width: 680px) {
  .tm-body {
    flex-direction: column;
    overflow: auto;
  }

  .tm-left,
  .tm-right {
    width: 100%;
    border-left: none;
    border-right: none;
  }

  .tm-left {
    border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  }

  .tm-center {
    min-height: 420px;
  }
}
.tm-access-title {
  margin-top: 14px;
}

.tm-access-card,
.tm-access-view {
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  padding: 10px;
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.03));
}

.tm-access-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tm-access-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.tm-access-select {
  width: 100%;
}

.tm-policy-row {
  display: grid;
  grid-template-columns: 1fr 1.6fr 32px;
  gap: 6px;
  align-items: center;
}

.tm-user-select {
  width: 100%;
}

.tm-access-view {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.tm-access-help,
.tm-dispatch-empty {
  padding: 9px 10px;
  border: 1px dashed var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 10px;
  background: var(--cpq-overlay-w3, rgba(255,255,255,0.03));
  color: var(--cpq-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.tm-policy-role-row {
  grid-template-columns: 1.05fr 1.6fr 32px;
}

.tm-policy-user-row {
  grid-template-columns: 1fr 1.6fr 32px;
}

.tm-user-exceptions {
  border: 1px dashed var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 10px;
  background: transparent;
}

.tm-user-exceptions :deep(.ant-collapse-header) {
  font-size: 11px;
  color: var(--cpq-text-secondary);
  padding: 8px 10px !important;
}

.tm-dispatch-rule-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  background: var(--cpq-overlay-w3, rgba(255,255,255,0.03));
}

.tm-dispatch-rule-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tm-dispatch-empty {
  text-align: center;
  color: var(--cpq-text-muted);
}
</style>
