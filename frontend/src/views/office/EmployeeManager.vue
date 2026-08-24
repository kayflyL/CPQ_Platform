<template>
  <div class="em-root">
    <aside class="em-list">
      <div class="em-list-head">
        <div>
          <div class="em-title">员工</div>
          <div class="em-subtitle">管理、设置和新建 AI 同事</div>
        </div>
        <a-button size="small" type="primary" @click="openCreate">新建员工</a-button>
      </div>

      <button
        v-for="colleague in colleagues"
        :key="colleague.role_key"
        class="em-member"
        :class="{ active: colleague.role_key === selectedRoleKey }"
        type="button"
        @click="selectColleague(colleague.role_key)"
      >
        <span class="em-dot" :style="{ background: colleague.color || '#1677ff' }"></span>
        <span class="em-name">{{ colleague.name || colleague.role_key }}</span>
        <span class="em-role">{{ colleague.role_key }}</span>
      </button>
    </aside>

    <section class="em-form">
      <template v-if="draft">
        <div class="em-card">
          <div class="em-card-title">基础信息</div>
          <div class="em-grid">
            <label class="em-field">
              <span>名称</span>
              <a-input v-model:value="draft.name" />
            </label>
            <label class="em-field">
              <span>角色标识</span>
              <a-input :value="draft.role_key" disabled />
            </label>
            <label class="em-field">
              <span>头像 URL</span>
              <a-input v-model:value="draft.avatar_url" placeholder="https://…，留空显示首字" />
            </label>
            <label class="em-field">
              <span>主题色</span>
              <input v-model="draft.color" type="color" class="em-color" />
            </label>
          </div>

          <div class="em-grid em-grid-two">
            <label class="em-field">
              <span>启用</span>
              <a-switch v-model:checked="draft.enabled" />
            </label>
            <label class="em-field">
              <span>允许总助分派</span>
              <a-switch v-model:checked="draft.dispatchable" />
            </label>
            <label class="em-field">
              <span>回复风格</span>
              <a-radio-group v-model:value="draft.response_style">
                <a-radio value="brief">简洁</a-radio>
                <a-radio value="detailed">详细</a-radio>
              </a-radio-group>
            </label>
            <label class="em-field">
              <span>模型覆盖</span>
              <a-input v-model:value="draft.model_override" placeholder="留空使用默认模型" />
            </label>
          </div>

          <div class="em-grid">
            <label class="em-field">
              <span>最大 Tokens</span>
              <a-input-number v-model:value="draft.response_profile.max_tokens" :min="100" :max="32000" :step="100" placeholder="留空使用全局" />
            </label>
            <label class="em-field">
              <span>温度</span>
              <a-input-number v-model:value="draft.response_profile.temperature" :min="0" :max="2" :step="0.1" placeholder="留空使用全局" />
            </label>
            <label class="em-field em-field-wide">
              <span>详细度提示词</span>
              <a-textarea v-model:value="draft.response_profile.style_prompt" :auto-size="{ minRows: 2, maxRows: 4 }" placeholder="留空则按回复风格自动生成简洁/详细提示词" />
            </label>
          </div>

          <label class="em-field">
            <span>开场白</span>
            <a-textarea v-model:value="draft.opening_message" :auto-size="{ minRows: 2, maxRows: 4 }" />
          </label>

          <label class="em-field">
            <span>System Prompt / 人格</span>
            <a-textarea v-model:value="draft.system_prompt" :auto-size="{ minRows: 4, maxRows: 10 }" />
          </label>
        </div>

        <div class="em-card">
          <div class="em-card-title">能力与权限</div>
          <label class="em-field">
            <span>Skill</span>
            <a-select
              v-model:value="draft.skills"
              mode="multiple"
              :options="skillOptions"
              placeholder="选择该员工可使用的 Skill"
              style="width: 100%"
            />
          </label>
          <label class="em-field">
            <span>可用工具</span>
            <a-select
              v-model:value="draft.tool_ids"
              mode="multiple"
              :options="toolOptions"
              placeholder="从工具注册表选择"
              style="width: 100%"
            />
          </label>
          <label class="em-field">
            <span>负责页面</span>
            <a-select
              v-model:value="draft.entry_points"
              mode="multiple"
              :options="pageScopeOptions"
              placeholder="选择负责页面"
              style="width: 100%"
            />
          </label>
          <label class="em-field">
            <span>数据来源</span>
            <a-select v-model:value="draft.data_sources" mode="multiple" placeholder="选择数据来源" style="width: 100%" @change="onDataSourcesChange">
              <a-select-option v-for="item in scopeOptions.data_sources" :key="item.key" :value="item.key">
                <span :title="item.description">{{ item.key }}</span>
              </a-select-option>
            </a-select>
          </label>
          <label class="em-field">
            <span>权限策略</span>
            <a-select v-model:value="draft.permission_policy" style="width: 100%">
              <a-select-option value="readonly">只读</a-select-option>
              <a-select-option value="confirm_before_write">确认后写入</a-select-option>
            </a-select>
          </label>
        </div>

        <div class="em-card">
          <div class="em-card-title">行为偏好</div>
          <div class="em-grid">
            <label class="em-field">
              <span>允许自主走动</span>
              <a-switch v-model:checked="draft.behavior_profile.wander_enabled" />
            </label>
            <label class="em-field">
              <span>最短空闲秒</span>
              <a-input-number v-model:value="draft.behavior_profile.min_idle_seconds" :min="1" :step="1" />
            </label>
            <label class="em-field">
              <span>最长空闲秒</span>
              <a-input-number v-model:value="draft.behavior_profile.max_idle_seconds" :min="1" :step="1" />
            </label>
          </div>

          <div class="em-subtitle em-subtitle-spaced">偏好区域</div>
          <div v-for="(zone, index) in draft.behavior_profile.preferred_zones" :key="index" class="em-zone-row">
            <a-input v-model:value="zone.zone" placeholder="区域 id" />
            <a-input-number v-model:value="zone.weight" :min="0" :step="5" placeholder="权重" />
            <a-input v-model:value="zone.activity" placeholder="活动" />
            <a-button size="small" danger @click="removePreferredZone(Number(index))">删除</a-button>
          </div>
          <a-button size="small" @click="addPreferredZone">添加偏好区域</a-button>

          <label class="em-field">
            <span>空闲动作</span>
            <a-select
              v-model:value="draft.behavior_profile.preferred_idle_actions"
              mode="tags"
              :options="idleActionOptions"
              style="width: 100%"
              placeholder="如 sit_idle, look_around"
            />
          </label>
        </div>

        <div class="em-card">
          <div class="em-card-title">记忆</div>
          <div class="em-grid">
            <label class="em-field">
              <span>短期记忆 TTL（秒）</span>
              <a-input-number v-model:value="draft.memory.short_term_ttl_seconds" :min="60" :step="60" />
            </label>
            <label class="em-field">
              <span>长期记忆仓库</span>
              <a-input v-model:value="draft.memory.long_term_store" />
            </label>
          </div>
          <div class="em-memory-stats">
            <a-tag>共 {{ memorySummary.total }} 条</a-tag>
            <a-tag color="gold">置顶 {{ memorySummary.pinned }}</a-tag>
            <a-tag v-for="kind in memorySummary.types" :key="kind">{{ kind }}</a-tag>
          </div>
          <a-space style="margin-top: 10px">
            <a-button size="small" @click="openMemories">查看 / 编辑长期记忆</a-button>
            <a-button size="small" @click="openThreads">会话管理</a-button>
          </a-space>
        </div>

        <div class="em-card">
          <div class="em-card-title">情绪 / 日程 / 关系</div>
          <div class="em-grid">
            <label class="em-field">
              <span>启用情绪模型</span>
              <a-switch v-model:checked="draft.mood.enabled" />
            </label>
            <label class="em-field">
              <span>当前状态</span>
              <a-input v-model:value="draft.mood.state" />
            </label>
            <label class="em-field">
              <span>衰减时间（秒）</span>
              <a-input-number v-model:value="draft.mood.decay_seconds" :min="60" :step="60" />
            </label>
            <label class="em-field">
              <span>时区</span>
              <a-input v-model:value="draft.schedule.timezone" />
            </label>
            <label class="em-field">
              <span>工作时段</span>
              <a-input v-model:value="draft.schedule.work_hours" />
            </label>
            <label class="em-field">
              <span>偏好会议时间</span>
              <a-input v-model:value="draft.schedule.preferred_meeting_time" />
            </label>
          </div>

          <label class="em-field">
            <span>关系</span>
            <a-select v-model:value="draft.relations.peers" mode="tags" :options="peerOptions" style="width: 100%" placeholder="填写协作 peer role_key" />
          </label>

          <div class="em-grid">
            <label class="em-field">
              <span>偏好异步协作</span>
              <a-switch v-model:checked="draft.preferences.prefers_async" />
            </label>
            <label class="em-field">
              <span>会议最大时长（分钟）</span>
              <a-input-number v-model:value="draft.preferences.meeting_max_minutes" :min="5" :step="5" />
            </label>
          </div>
        </div>

        <div class="em-actions">
          <a-button danger :loading="saving" @click="confirmDelete">删除员工</a-button>
        </div>
      </template>
      <div v-else class="em-empty">选择左侧员工，或新建一位 AI 同事</div>
    </section>

    <a-modal v-model:open="memoryOpen" :title="`长期记忆：${draft?.name || draft?.role_key || ''}`" :footer="null" width="760">
      <div class="em-memory-toolbar">
        <a-input v-model:value="memoryKeyword" placeholder="搜索记忆内容" allow-clear style="width: 220px" @press-enter="loadMemories" />
        <a-button size="small" @click="loadMemories">刷新</a-button>
        <a-button size="small" type="primary" @click="openMemoryCreate">新建记忆</a-button>
        <a-popconfirm title="确定清空该员工全部长期记忆？" @confirm="clearMemories">
          <a-button size="small" danger>清空</a-button>
        </a-popconfirm>
      </div>
      <a-table
        :data-source="memories"
        :columns="memoryColumns"
        row-key="id"
        size="small"
        :loading="memoryLoading"
        :pagination="{ pageSize: 8, showSizeChanger: false }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'content'">
            <span>{{ record.message }}</span>
          </template>
          <template v-else-if="column.key === 'meta'">
            <a-space size="small" wrap>
              <a-tag>{{ record.payload?.kind || 'episodic' }}</a-tag>
              <a-tag color="blue">重要度 {{ record.payload?.importance ?? 0.5 }}</a-tag>
              <a-tag v-if="record.payload?.pinned" color="gold">置顶</a-tag>
            </a-space>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space size="small">
              <a-button size="small" @click="editMemory(record)">编辑</a-button>
              <a-popconfirm title="删除这条长期记忆？" @confirm="deleteMemory(record)">
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
      <div class="em-memory-editor">
        <a-textarea v-model:value="memoryForm.content" :auto-size="{ minRows: 2, maxRows: 5 }" placeholder="记忆内容" />
        <a-input v-model:value="memoryForm.kind" placeholder="类型，如 semantic / episodic" style="width: 180px" />
        <a-input-number v-model:value="memoryForm.importance" :min="0" :max="1" :step="0.1" style="width: 110px" placeholder="重要度" />
        <a-switch v-model:checked="memoryForm.pinned" checked-children="置顶" un-checked-children="普通" />
        <a-button type="primary" size="small" :loading="memorySaving" @click="saveMemory">保存</a-button>
        <a-button v-if="editingMemoryId" size="small" @click="resetMemoryForm">取消编辑</a-button>
      </div>
    </a-modal>

    <a-modal
      v-model:open="threadsOpen"
      :title="`会话管理：${draft?.name || draft?.role_key || ''}`"
      :footer="null"
      width="880"
    >
      <div class="em-thread-toolbar">
        <a-button size="small" @click="loadThreads">刷新</a-button>
      </div>
      <a-tabs v-model:activeKey="threadTab">
        <a-tab-pane key="normal" tab="正常会话">
          <a-table
            :data-source="normalThreads"
            :columns="threadColumns"
            row-key="thread_id"
            size="small"
            :loading="threadsLoading"
            :pagination="{ pageSize: 8, showSizeChanger: false }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'title'">
                <a-button type="link" size="small" @click="viewThread(record)">
                  {{ threadDisplayTitle(record) }}
                </a-button>
              </template>
              <template v-else-if="column.key === 'updated_at'">
                {{ formatThreadTime(record.updated_at) }}
              </template>
              <template v-else-if="column.key === 'action'">
                <a-space size="small">
                  <a-button size="small" @click="viewThread(record)">查看</a-button>
                  <a-button size="small" @click="openRenameThread(record)">重命名</a-button>
                  <a-popconfirm title="删除该会话？" @confirm="deleteThread(record)">
                    <a-button size="small" danger>删除</a-button>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </a-tab-pane>
        <a-tab-pane key="deleted" tab="回收站">
          <a-table
            :data-source="deletedThreads"
            :columns="threadColumns"
            row-key="thread_id"
            size="small"
            :loading="threadsLoading"
            :pagination="{ pageSize: 8, showSizeChanger: false }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'title'">
                <a-button type="link" size="small" @click="viewThread(record)">
                  {{ threadDisplayTitle(record) }}
                </a-button>
              </template>
              <template v-else-if="column.key === 'updated_at'">
                {{ formatThreadTime(record.updated_at) }}
              </template>
              <template v-else-if="column.key === 'action'">
                <a-space size="small">
                  <a-button size="small" @click="viewThread(record)">查看</a-button>
                  <a-popconfirm title="恢复该会话？" @confirm="restoreThread(record)">
                    <a-button size="small">恢复</a-button>
                  </a-popconfirm>
                  <a-popconfirm title="彻底删除后将无法恢复？" @confirm="purgeThread(record)">
                    <a-button size="small" danger>彻底删除</a-button>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </a-tab-pane>
      </a-tabs>
    </a-modal>

    <a-modal v-model:open="threadMessagesOpen" title="会话消息" :footer="null" width="640">
      <div class="em-thread-messages">
        <div v-for="msg in threadMessages" :key="msg.message_id" class="em-thread-message">
          <span class="em-msg-role">{{ msg.role }}</span>
          <p>{{ msg.content }}</p>
        </div>
        <a-empty v-if="!threadMessages.length" description="暂无消息" />
      </div>
    </a-modal>

    <a-modal
      v-model:open="renameThreadOpen"
      title="重命名会话"
      :confirm-loading="renameThreadSaving"
      @ok="saveRenameThread"
    >
      <a-input v-model:value="renameThreadForm.title" placeholder="输入会话标题" allow-clear />
    </a-modal>

    <a-modal v-model:open="createOpen" title="新建 AI 同事" :footer="null" width="520">
      <div class="em-modal-form">
        <label class="em-field">
          <span>角色标识</span>
          <a-input v-model:value="createForm.role_key" placeholder="唯一英文标识，如 data_analyst" />
        </label>
        <label class="em-field">
          <span>名称</span>
          <a-input v-model:value="createForm.name" placeholder="如 数据分析师" />
        </label>
        <label class="em-field">
          <span>开场白</span>
          <a-textarea v-model:value="createForm.opening_message" :auto-size="{ minRows: 2, maxRows: 4 }" />
        </label>
        <label class="em-field">
          <span>主题色</span>
          <input v-model="createForm.color" type="color" class="em-color" />
        </label>
      </div>
      <div class="em-modal-actions">
        <a-button @click="createOpen = false">取消</a-button>
        <a-button type="primary" :loading="saving" @click="handleCreate">创建</a-button>
      </div>
    </a-modal>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { assistantApi, type AssistantMessage, type AssistantThread } from '@/api/assistant'
import { officeApi } from '@/api/office'
import { deriveDataSources, manualDataSources as getManualDataSources, reconcileDataSources } from '@/utils/scopeOptions'

const props = defineProps<{
  colleagues: any[]
  initialRoleKey?: string | null
}>()

const emit = defineEmits<{ (e: 'saved'): void }>()

const selectedRoleKey = ref<string | null>(props.initialRoleKey || null)
const draft = ref<Record<string, any> | null>(null)
const saving = ref(false)
const createOpen = ref(false)
const createForm = ref({
  role_key: '',
  name: '',
  opening_message: '',
  color: '#1677ff',
})
const tools = ref<any[]>([])
const skills = ref<any[]>([])
const memorySummary = ref({ total: 0, pinned: 0, types: [] as string[] })

const memoryOpen = ref(false)
const memoryLoading = ref(false)
const memorySaving = ref(false)
const memoryKeyword = ref('')
const memories = ref<any[]>([])
const editingMemoryId = ref<number | null>(null)
const memoryForm = ref({ content: '', kind: 'semantic', importance: 0.5, pinned: false })
const memoryColumns = [
  { title: '记忆内容', key: 'content', width: 320 },
  { title: '属性', key: 'meta', width: 200 },
  { title: '操作', key: 'action', width: 120 },
]

const threadsOpen = ref(false)
const threadsLoading = ref(false)
const threadTab = ref<'normal' | 'deleted'>('normal')
const allThreads = ref<AssistantThread[]>([])
const threadMessagesOpen = ref(false)
const threadMessages = ref<AssistantMessage[]>([])
const renameThreadOpen = ref(false)
const renameThreadSaving = ref(false)
const renameThreadForm = ref<{ threadId: string; title: string }>({ threadId: '', title: '' })
const threadColumns = [
  { title: '会话', key: 'title', ellipsis: true },
  { title: '最后消息', key: 'last_message', ellipsis: true },
  { title: '消息数', key: 'msg_count', width: 80 },
  { title: '创建人', key: 'created_by_name', width: 120 },
  { title: '更新时间', key: 'updated_at', width: 160 },
  { title: '操作', key: 'action', width: 190 },
]

const idleActionOptions = ['sit_idle', 'look_around', 'check_notes', 'window', 'stand', 'wave'].map((value) => ({ value, label: value }))
const toolOptions = computed(() => tools.value.map((tool) => ({ value: tool.name, label: tool.name })))
const skillOptions = computed(() =>
  skills.value.map((skill) => ({ value: skill.key, label: skill.name || skill.key })),
)
const peerOptions = computed(() =>
  props.colleagues.filter((c) => c.role_key !== selectedRoleKey.value).map((c) => ({ value: c.role_key, label: c.name || c.role_key })),
)
const normalThreads = computed(() => allThreads.value.filter((t) => !t.deleted_at))
const deletedThreads = computed(() => allThreads.value.filter((t) => t.deleted_at))

const scopeOptions = ref<{ data_sources: any[]; page_scopes: any[] }>({ data_sources: [], page_scopes: [] })
const manualSourcesRef = ref<string[]>([])
const pageScopeOptions = computed(() => scopeOptions.value.page_scopes.map((item) => ({ value: item.key, label: item.label || item.key })))
async function loadScopeOptions() {
  try {
    scopeOptions.value = await officeApi.scopeOptions()
  } catch {
    scopeOptions.value = { data_sources: [], page_scopes: [] }
  } finally {
    initializeManualDataSources()
    applyDataSources()
  }
}
loadScopeOptions()

function initializeManualDataSources() {
  if (!draft.value) return
  manualSourcesRef.value = getManualDataSources(draft.value.data_sources, draft.value.entry_points, scopeOptions.value)
}

function applyDataSources() {
  if (!draft.value) return
  const derived = deriveDataSources(draft.value.entry_points, scopeOptions.value)
  draft.value.data_sources = Array.from(new Set([...manualSourcesRef.value, ...derived]))
}

function onDataSourcesChange() {
  if (!draft.value) return
  manualSourcesRef.value = getManualDataSources(draft.value.data_sources, draft.value.entry_points, scopeOptions.value)
}

watch(
  () => draft.value?.entry_points,
  (newPages, oldPages) => {
    if (!draft.value) return
    draft.value.data_sources = reconcileDataSources(
      draft.value.data_sources,
      oldPages,
      newPages,
      scopeOptions.value,
    )
    manualSourcesRef.value = getManualDataSources(
      draft.value.data_sources,
      newPages,
      scopeOptions.value,
    )
  },
)

function defaultDraft(source: any = {}) {
  return {
    role_key: source.role_key || '',
    name: source.name || source.role_key || '',
    avatar_url: source.avatar_url || '',
    color: source.color || '#1677ff',
    enabled: source.enabled ?? true,
    system_prompt: source.system_prompt || '',
    opening_message: source.opening_message || '',
    response_style: source.response_style || source.response_profile?.style || 'detailed',
    response_profile: {
      style: source.response_profile?.style || source.response_style || 'detailed',
      max_tokens: source.response_profile?.max_tokens ?? null,
      temperature: source.response_profile?.temperature ?? null,
      style_prompt: source.response_profile?.style_prompt || '',
    },
    model_override: source.model_override || null,
    tool_ids: Array.isArray(source.tool_ids) ? [...source.tool_ids] : [],
    data_sources: Array.isArray(source.data_sources) ? [...source.data_sources] : [],
    entry_points: Array.isArray(source.entry_points) ? [...source.entry_points] : [],
    permission_policy: source.permission_policy || 'readonly',
    dispatchable: source.dispatchable ?? true,
    behavior_profile: {
      wander_enabled: source.behavior_profile?.wander_enabled ?? true,
      min_idle_seconds: source.behavior_profile?.min_idle_seconds ?? 8,
      max_idle_seconds: source.behavior_profile?.max_idle_seconds ?? 20,
      preferred_zones: Array.isArray(source.behavior_profile?.preferred_zones)
        ? JSON.parse(JSON.stringify(source.behavior_profile.preferred_zones))
        : [
            { zone: 'desk_zone', weight: 55, activity: '在工位整理工作' },
            { zone: 'public_zone', weight: 30, activity: '去公共区看看' },
            { zone: 'meeting_room', weight: 15, activity: '去会议室整理资料' },
          ],
      preferred_idle_actions: Array.isArray(source.behavior_profile?.preferred_idle_actions)
        ? [...source.behavior_profile.preferred_idle_actions]
        : ['sit_idle', 'look_around', 'check_notes'],
    },
    memory: {
      short_term_ttl_seconds: source.memory?.short_term_ttl_seconds ?? 3600,
      long_term_store: source.memory?.long_term_store || 'office_memory',
    },
    mood: {
      enabled: source.mood?.enabled ?? true,
      state: source.mood?.state || 'calm',
      decay_seconds: source.mood?.decay_seconds ?? 900,
    },
    schedule: {
      timezone: source.schedule?.timezone || 'Asia/Shanghai',
      work_hours: source.schedule?.work_hours || '09:00-18:00',
      preferred_meeting_time: source.schedule?.preferred_meeting_time || '10:00-11:30',
    },
    relations: {
      default: source.relations?.default || 'colleague',
      peers: Array.isArray(source.relations?.peers) ? [...source.relations.peers] : [],
    },
    preferences: {
      prefers_async: source.preferences?.prefers_async ?? true,
      meeting_max_minutes: source.preferences?.meeting_max_minutes ?? 25,
    },
    skills: Array.isArray(source.skills)
      ? source.skills.map((item: any) => (typeof item === 'string' ? item : item?.key)).filter(Boolean)
      : [],
  }
}

function selectColleague(roleKey: string) {
  selectedRoleKey.value = roleKey
}

watch(
  selectedRoleKey,
  (roleKey) => {
    const colleague = props.colleagues.find((c) => c.role_key === roleKey)
    draft.value = colleague ? defaultDraft(colleague) : null
    initializeManualDataSources()
    applyDataSources()
    loadMemorySummary()
  },
  { immediate: true },
)

watch(
  () => props.colleagues,
  (colleagues) => {
    if (!colleagues.find((c) => c.role_key === selectedRoleKey.value)) {
      selectedRoleKey.value = colleagues[0]?.role_key || null
    }
  },
  { immediate: true, deep: true },
)

async function loadTools() {
  try {
    tools.value = await assistantApi.tools.catalog()
  } catch {
    tools.value = []
  }
}

loadTools()

async function loadSkills() {
  try {
    skills.value = await officeApi.listSkills()
  } catch {
    skills.value = []
  }
}

loadSkills()


async function loadMemorySummary() {
  const roleKey = draft.value?.role_key
  if (!roleKey) {
    memorySummary.value = { total: 0, pinned: 0, types: [] }
    return
  }
  try {
    const data = await officeApi.listMemories({ role_key: roleKey, limit: 50 })
    const items = Array.isArray(data.memories) ? data.memories : []
    const typeCounts = new Map<string, number>()
    for (const item of items) {
      const kind = String(item?.payload?.kind || 'episodic')
      typeCounts.set(kind, (typeCounts.get(kind) || 0) + 1)
    }
    memorySummary.value = {
      total: Number(data.total ?? items.length),
      pinned: items.filter((item) => !!item?.payload?.pinned).length,
      types: [...typeCounts.entries()].map(([kind, count]) => `${kind} ${count}`),
    }
  } catch {
    memorySummary.value = { total: 0, pinned: 0, types: [] }
  }
}

function resetMemoryForm() {
  editingMemoryId.value = null
  memoryForm.value = { content: '', kind: 'semantic', importance: 0.5, pinned: false }
}

async function loadMemories() {
  if (!draft.value?.role_key) return
  memoryLoading.value = true
  try {
    const data = await officeApi.listMemories({
      role_key: draft.value.role_key,
      keyword: memoryKeyword.value.trim() || undefined,
    })
    memories.value = Array.isArray(data.memories) ? data.memories : []
    await loadMemorySummary()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '长期记忆加载失败')
  } finally {
    memoryLoading.value = false
  }
}

function openMemories() {
  if (!draft.value?.role_key) return
  memoryKeyword.value = ''
  resetMemoryForm()
  memoryOpen.value = true
  loadMemories()
}

function openMemoryCreate() {
  resetMemoryForm()
}

function editMemory(record: any) {
  editingMemoryId.value = Number(record.id)
  memoryForm.value = {
    content: record.message || '',
    kind: record.payload?.kind || 'semantic',
    importance: Number(record.payload?.importance ?? 0.5),
    pinned: !!record.payload?.pinned,
  }
}

async function saveMemory() {
  if (!draft.value?.role_key) return
  const content = memoryForm.value.content.trim()
  if (!content) {
    message.warning('请填写记忆内容')
    return
  }
  memorySaving.value = true
  try {
    if (editingMemoryId.value) {
      await officeApi.updateMemory(editingMemoryId.value, {
        content,
        kind: memoryForm.value.kind,
        importance: memoryForm.value.importance,
        pinned: memoryForm.value.pinned,
      })
      message.success('已更新记忆')
    } else {
      await officeApi.createMemory({
        role_key: draft.value.role_key,
        content,
        kind: memoryForm.value.kind,
        importance: memoryForm.value.importance,
        pinned: memoryForm.value.pinned,
      })
      message.success('已新建记忆')
    }
    resetMemoryForm()
    await loadMemories()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '长期记忆保存失败')
  } finally {
    memorySaving.value = false
  }
}

async function deleteMemory(record: any) {
  try {
    await officeApi.deleteMemory(Number(record.id))
    message.success('已删除记忆')
    await loadMemories()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '删除记忆失败')
  }
}

async function clearMemories() {
  if (!draft.value?.role_key) return
  try {
    await officeApi.clearMemories(draft.value.role_key)
    message.success('已清空该员工长期记忆')
    memories.value = []
    await loadMemorySummary()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '清空记忆失败')
  }
}

async function openThreads() {
  if (!draft.value?.role_key) return
  threadTab.value = 'normal'
  threadsOpen.value = true
  await loadThreads()
}

async function loadThreads() {
  if (!draft.value?.role_key) return
  threadsLoading.value = true
  try {
    allThreads.value = await assistantApi.threads.listAll({
      thread_kind: 'office_colleague',
      role_key: draft.value.role_key,
    })
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '会话列表加载失败')
  } finally {
    threadsLoading.value = false
  }
}

function threadDisplayTitle(record: AssistantThread) {
  return record.title || record.first_message || record.last_message || '未命名会话'
}

function formatThreadTime(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

async function viewThread(record: AssistantThread) {
  try {
    threadMessages.value = await assistantApi.threads.messages(record.thread_id, 100)
    threadMessagesOpen.value = true
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '会话消息加载失败')
  }
}

function openRenameThread(record: AssistantThread) {
  renameThreadForm.value = { threadId: record.thread_id, title: record.title || '' }
  renameThreadOpen.value = true
}

async function saveRenameThread() {
  const title = renameThreadForm.value.title.trim()
  if (!title) {
    message.warning('请填写会话标题')
    return
  }
  renameThreadSaving.value = true
  try {
    await assistantApi.threads.rename(renameThreadForm.value.threadId, title)
    message.success('已重命名会话')
    renameThreadOpen.value = false
    await loadThreads()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '重命名会话失败')
  } finally {
    renameThreadSaving.value = false
  }
}

async function deleteThread(record: AssistantThread) {
  try {
    await assistantApi.threads.remove(record.thread_id)
    message.success('会话已移入回收站')
    await loadThreads()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '删除会话失败')
  }
}

async function restoreThread(record: AssistantThread) {
  try {
    await assistantApi.threads.restore(record.thread_id)
    message.success('会话已恢复')
    await loadThreads()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '恢复会话失败')
  }
}

async function purgeThread(record: AssistantThread) {
  try {
    await assistantApi.threads.purge(record.thread_id)
    message.success('会话已彻底删除')
    await loadThreads()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '彻底删除会话失败')
  }
}

function addPreferredZone() {
  draft.value?.behavior_profile.preferred_zones.push({ zone: 'public_zone', weight: 20, activity: '去公共区看看' })
}

function removePreferredZone(index: number) {
  draft.value?.behavior_profile.preferred_zones.splice(index, 1)
}

function openCreate() {
  createForm.value = { role_key: '', name: '', opening_message: '', color: '#1677ff' }
  createOpen.value = true
}

async function handleCreate() {
  const roleKey = createForm.value.role_key.trim()
  if (!roleKey) {
    message.warning('请填写角色标识')
    return
  }
  saving.value = true
  try {
    await officeApi.createColleague({
      role_key: roleKey,
      name: createForm.value.name.trim() || roleKey,
      opening_message: createForm.value.opening_message,
      color: createForm.value.color || '#1677ff',
      enabled: true,
      permission_policy: 'readonly',
    })
    createOpen.value = false
    selectedRoleKey.value = roleKey
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '新建员工失败')
  } finally {
    saving.value = false
  }
}

async function save() {
  if (!draft.value?.role_key) return
  if (draft.value.response_profile) draft.value.response_profile.style = draft.value.response_style || 'detailed'
  saving.value = true
  try {
    await officeApi.updateColleague(draft.value.role_key, draft.value)
    message.success(`已保存 ${draft.value.role_key}`)
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '保存员工失败')
  } finally {
    saving.value = false
  }
}

function confirmDelete() {
  if (!draft.value) return
  Modal.confirm({
    title: `删除 AI 员工「${draft.value.name || draft.value.role_key}」？`,
    content: '删除后该员工配置及关联房间分配会一并移除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: deleteEmployee,
  })
}

async function deleteEmployee() {
  if (!draft.value) return
  saving.value = true
  try {
    await officeApi.deleteColleague(draft.value.role_key)
    message.success(`已删除 ${draft.value.role_key}`)
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '删除员工失败')
  } finally {
    saving.value = false
  }
}

defineExpose({ openCreate, save })
</script>

<style scoped>
.em-root {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.em-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  overflow: auto;
}

.em-list-head,
.em-card-title,
.em-subtitle {
  font-weight: 800;
}

.em-title {
  font-size: 16px;
}

.em-subtitle {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.em-subtitle-spaced {
  margin: 14px 0 8px;
}

.em-member {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--cpq-text-primary);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.em-member:hover,
.em-member.active {
  border-color: rgba(22, 119, 255, 0.35);
  background: rgba(22, 119, 255, 0.1);
}

.em-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.em-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 700;
}

.em-role {
  margin-left: auto;
  color: var(--cpq-text-muted);
  font-size: 11px;
}

.em-form {
  min-height: 0;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  overflow: auto;
}

.em-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.em-card-title {
  color: var(--cpq-text-primary);
  font-size: 13px;
}

.em-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.em-grid-two {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.em-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.em-field-wide {
  grid-column: 1 / -1;
}

.em-color {
  width: 48px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
}

.em-zone-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 90px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.em-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 12px;
}

.em-empty {
  display: grid;
  height: 100%;
  place-items: center;
  color: var(--cpq-text-muted);
}

.em-modal-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.em-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}

.em-thread-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}

.em-thread-messages {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
}

.em-thread-message {
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
}

.em-thread-message p {
  margin: 6px 0 0;
  color: var(--cpq-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.em-msg-role {
  color: var(--cpq-text-muted);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.em-memory-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.em-memory-editor {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.em-memory-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
</style>
