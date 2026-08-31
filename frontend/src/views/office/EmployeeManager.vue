<template>
  <div class="em-root">
    <div class="em-cards-head">
      <div>
        <div class="em-title">员工</div>
        <div class="em-subtitle">管理、设置和新建 AI 同事</div>
      </div>
      <a-button size="small" type="primary" @click="openCreate">新建员工</a-button>
    </div>

    <div class="em-cards">
      <RippleRevealCard
        v-for="colleague in colleagues"
        :key="colleague.role_key"
        :colleague="colleague"
        @open="openEditorFor(colleague.role_key)"
      />
    </div>


    <a-modal
      v-model:open="editorOpen"
      :footer="null"
      width="1080"
      wrap-class-name="em-editor-modal"
      :title="`编辑员工：${draft?.name || draft?.role_key || ''}`"
    >
      <div class="em-form">

      <template v-if="draft">
        <div class="em-card">
          <div class="em-card-title">身份</div>
          <div class="em-identity-cols">
            <div class="em-identity-left">
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
            <label class="em-field">
              <span>启用</span>
              <a-switch v-model:checked="draft.enabled" />
            </label>
            <label class="em-field">
              <span>允许总助分派</span>
              <a-switch v-model:checked="draft.dispatchable" />
            </label>
          </div>

          <label class="em-field">
            <span>开场白</span>
            <a-textarea v-model:value="draft.opening_message" :auto-size="{ minRows: 2, maxRows: 4 }" />
          </label>
            </div>
            <div class="em-identity-right">
              <label class="em-field">
                <span>虚拟形象</span>
                <a-select v-model:value="draft.pet_model" dropdown-class-name="em-pet-select-dropdown" style="width:100%">
                  <a-select-option v-for="m in PET_MODEL_CATALOG" :key="m.key" :value="m.key">{{ m.label }}</a-select-option>
                </a-select>
              </label>
              <div class="em-pet-preview">
                <Live2dPreview :model-key="draft.pet_model" :bg-color="draft.color" />
              </div>
            </div>
          </div>
        </div>

        <div class="em-card">
          <div class="em-card-title">指令（大脑）</div>
          <label class="em-field">
            <span>System Prompt / 人格</span>
            <a-textarea v-model:value="draft.system_prompt" :auto-size="{ minRows: 5, maxRows: 12 }" placeholder="定义这位同事的性格、职责边界和说话方式" />
          </label>
          <div class="em-field">
            <span>回复风格</span>
            <a-radio-group v-model:value="draft.response_profile.style_mode">
              <a-radio value="brief">简洁</a-radio>
              <a-radio value="detailed">详细</a-radio>
              <a-radio value="custom">自定义</a-radio>
            </a-radio-group>
          </div>
          <label v-if="draft.response_profile.style_mode === 'custom'" class="em-field">
            <span>自定义风格提示词</span>
            <a-textarea v-model:value="draft.response_profile.style_prompt" :auto-size="{ minRows: 2, maxRows: 4 }" placeholder="例：先给结论再展开，语气活泼，适度使用表情符号 😊" />
          </label>

          <div class="em-param-head">
            <span class="em-subtitle">模型参数</span>
            <a-input v-model:value="draft.model_override" class="em-param-model" placeholder="模型覆盖：留空用全局默认模型" />
          </div>
          <div class="em-param-grid">
            <div class="em-slider-field">
              <div class="em-slider-head">
                <span>温度</span>
                <a v-if="tempCustomized" class="em-slider-reset" @click="draft.response_profile.temperature = null">跟随全局</a>
              </div>
              <a-slider
                v-model:value="tempValue"
                :min="0"
                :max="1.5"
                :step="0.1"
                :marks="TEMP_MARKS"
                :tip-formatter="(v: number) => v.toFixed(1)"
              />
              <div class="em-slider-hint">
                <a-tag :color="tempHint.color">{{ tempHint.label }}</a-tag>
                <span>{{ tempHint.text }}</span>
              </div>
            </div>
            <div class="em-slider-field">
              <div class="em-slider-head">
                <span>最大 Tokens</span>
                <a v-if="tokenCustomized" class="em-slider-reset" @click="draft.response_profile.max_tokens = null">跟随全局</a>
              </div>
              <a-slider
                v-model:value="tokenValue"
                :min="8000"
                :max="64000"
                :step="1000"
                :marks="TOKEN_MARKS"
                :tip-formatter="(v: number) => String(v)"
              />
              <div class="em-slider-hint">
                <a-tag :color="tokenHint.color">{{ tokenHint.label }}</a-tag>
                <span>{{ tokenHint.text }}</span>
              </div>
            </div>
          </div>
          <div class="em-param-note">Skill 业务问答固定低温 0.2，不受以上滑杆影响</div>
        </div>

        <div class="em-card">
          <div class="em-card-title">能力</div>
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
            <span>数据来源</span>
            <a-select v-model:value="draft.data_sources" mode="multiple" placeholder="选择数据来源" style="width: 100%">
              <a-select-option v-for="item in scopeOptions.data_sources" :key="item.key" :value="item.key">
                <span :title="item.description">{{ item.label || item.key }}</span>
              </a-select-option>
            </a-select>
          </label>
        </div>

        <div class="em-card">
          <div class="em-card-title">记忆</div>
          <div class="em-grid">
            <label class="em-field">
              <span>启用长期记忆</span>
              <a-switch v-model:checked="draft.memory_policy.enabled" />
            </label>
            <label class="em-field">
              <span>对话后自动学习</span>
              <a-switch v-model:checked="draft.memory_policy.auto_memory" />
            </label>
          </div>
          <div class="em-memory-stats">
            <a-tag>共 {{ memorySummary.total }} 条</a-tag>
            <a-tag color="gold">置顶 {{ memorySummary.pinned }}</a-tag>
            <a-tag v-for="item in memorySummary.byType" :key="item.type" :color="typeMeta(item.type).color">
              {{ typeMeta(item.type).label }} {{ item.count }}
            </a-tag>
          </div>
          <div class="em-subtitle em-memory-hint">记忆是提炼过的长期事实与偏好（用户画像 / 偏好 / 业务事实 / 行为指引），每轮对话后由后台自动归并，注入后续对话的系统提示。</div>
          <a-space style="margin-top: 10px">
            <a-button size="small" @click="openMemories">管理记忆</a-button>
            <a-button size="small" @click="openThreads">会话管理</a-button>
          </a-space>
        </div>

        <a-collapse class="em-advanced" :bordered="false">
          <a-collapse-panel key="behavior" header="3D 办公室行为">
            <div class="em-grid">
              <label class="em-field">
                <span>允许自主走动</span>
                <a-switch v-model:checked="draft.behavior_profile.wander_enabled" />
              </label>
              <label class="em-field">
                <span>最短空闲秒</span>
                <a-input-number v-model:value="draft.behavior_profile.min_idle_seconds" :min="1" :step="1" style="width: 100%" />
              </label>
              <label class="em-field">
                <span>最长空闲秒</span>
                <a-input-number v-model:value="draft.behavior_profile.max_idle_seconds" :min="1" :step="1" style="width: 100%" />
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

            <label class="em-field" style="margin-top: 12px">
              <span>空闲动作</span>
              <a-select
                v-model:value="draft.behavior_profile.preferred_idle_actions"
                mode="tags"
                :options="idleActionOptions"
                style="width: 100%"
                placeholder="如 sit_idle, look_around"
              />
            </label>
          </a-collapse-panel>
        </a-collapse>

        <div class="em-actions">
          <a-button type="primary" :loading="saving" @click="save">保存</a-button>
          <a-button danger :loading="saving" @click="confirmDelete">删除员工</a-button>
        </div>
      </template>
      <div v-else class="em-empty">选择左侧员工，或新建一位 AI 同事</div>

      <ColleagueAccessPanel class="em-access-panel" :colleagues="colleagues" @saved="emit('saved')" />
      </div>
    </a-modal>

    <a-modal v-model:open="memoryOpen" :title="`长期记忆：${draft?.name || draft?.role_key || ''}`" :footer="null" width="720">
      <div class="em-memory-toolbar">
        <a-input-search
          v-model:value="memoryKeyword"
          placeholder="搜索记忆内容"
          allow-clear
          style="width: 240px"
          @search="loadMemories"
        />
        <a-button size="small" @click="loadMemories">刷新</a-button>
        <a-button size="small" type="primary" @click="openMemoryCreate">新建记忆</a-button>
        <a-popconfirm title="确定清空该员工全部长期记忆？" @confirm="clearMemories">
          <a-button size="small" danger>清空</a-button>
        </a-popconfirm>
      </div>

      <div v-if="memoryEditorOpen" class="em-memory-editor">
        <a-select v-model:value="memoryForm.type" style="width: 150px" :options="memoryTypeOptions" />
        <a-textarea v-model:value="memoryForm.content" :auto-size="{ minRows: 2, maxRows: 5 }" placeholder="一句压缩事实，如：报价默认含三年质保" style="flex: 1" />
        <a-switch v-model:checked="memoryForm.pinned" checked-children="置顶" un-checked-children="普通" />
        <a-button type="primary" size="small" :loading="memorySaving" @click="saveMemory">保存</a-button>
        <a-button size="small" @click="resetMemoryForm">取消</a-button>
      </div>

      <a-spin :spinning="memoryLoading">
        <div class="em-memory-list">
          <div v-for="item in memories" :key="item.id" class="em-memory-item" :class="{ pinned: item.pinned }">
            <a-tag :color="typeMeta(item.type).color" class="em-memory-type">{{ item.type_label || typeMeta(item.type).label }}</a-tag>
            <div class="em-memory-body">
              <div class="em-memory-content">{{ item.content }}</div>
              <div class="em-memory-meta">
                <span>{{ item.source === 'manual' ? '手动' : '自动学习' }}</span>
                <span v-if="item.updated_at">{{ formatMemoryTime(item.updated_at) }}</span>
              </div>
            </div>
            <div class="em-memory-actions">
              <a-button size="small" type="text" :title="item.pinned ? '取消置顶' : '置顶'" @click="toggleMemoryPinned(item)">
                <span class="em-memory-star" :class="{ on: item.pinned }">★</span>
              </a-button>
              <a-button size="small" type="text" @click="editMemory(item)">编辑</a-button>
              <a-popconfirm title="删除这条记忆？" @confirm="deleteMemory(item)">
                <a-button size="small" type="text" danger>删除</a-button>
              </a-popconfirm>
            </div>
          </div>
          <a-empty v-if="!memories.length && !memoryLoading" description="暂无记忆，对话中产生的长期事实与偏好会自动出现在这里" />
        </div>
      </a-spin>
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
import { officeApi, type OfficeColleagueMemory } from '@/api/office'
import ColleagueAccessPanel from './ColleagueAccessPanel.vue'
import Live2dPreview from '@/components/assistant/Live2dPreview.vue'
import RippleRevealCard from '@/components/office/RippleRevealCard.vue'
import { PET_MODEL_CATALOG } from '@/store/petModel'

const props = defineProps<{
  colleagues: any[]
  initialRoleKey?: string | null
}>()

const emit = defineEmits<{ (e: 'saved'): void }>()

const MEMORY_TYPE_META: Record<string, { label: string; color: string }> = {
  user_profile: { label: '用户画像', color: 'blue' },
  preference: { label: '偏好反馈', color: 'purple' },
  business_fact: { label: '业务事实', color: 'green' },
  guide: { label: '行为指引', color: 'orange' },
}
const memoryTypeOptions = Object.entries(MEMORY_TYPE_META).map(([value, meta]) => ({ value, label: meta.label }))

function typeMeta(type: string) {
  return MEMORY_TYPE_META[type] || { label: type || '未分类', color: 'default' }
}

const selectedRoleKey = ref<string | null>(props.initialRoleKey || null)
const draft = ref<Record<string, any> | null>(null)
const saving = ref(false)
const createOpen = ref(false)
const editorOpen = ref(false)
const createForm = ref({
  role_key: '',
  name: '',
  opening_message: '',
  color: '#1677ff',
})
const tools = ref<any[]>([])
const skills = ref<any[]>([])
const memorySummary = ref({ total: 0, pinned: 0, byType: [] as Array<{ type: string; count: number }> })

const memoryOpen = ref(false)
const memoryLoading = ref(false)
const memorySaving = ref(false)
const memoryKeyword = ref('')
const memories = ref<OfficeColleagueMemory[]>([])
const memoryEditorOpen = ref(false)
const editingMemoryId = ref<number | null>(null)
const memoryForm = ref({ type: 'business_fact', content: '', pinned: false })

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
const normalThreads = computed(() => allThreads.value.filter((t) => !t.deleted_at))
const deletedThreads = computed(() => allThreads.value.filter((t) => t.deleted_at))

const scopeOptions = ref<{ data_sources: any[]; page_scopes: any[] }>({ data_sources: [], page_scopes: [] })
async function loadScopeOptions() {
  try {
    scopeOptions.value = await officeApi.scopeOptions()
  } catch {
    scopeOptions.value = { data_sources: [], page_scopes: [] }
  }
}
loadScopeOptions()

const GLOBAL_TEMP = 0.7
const GLOBAL_TOKENS = 16000
const TEMP_MARKS = { 0: '0', 0.7: '0.7', 1.5: '1.5' }
const TOKEN_MARKS = { 8000: '8k', 16000: '16k', 32000: '32k', 64000: '64k' }

watch(() => draft.value?.response_profile?.style_mode, (mode) => {
  if (!mode || !draft.value?.response_profile) return
  if (mode !== 'custom') {
    draft.value.response_profile.style_prompt = ''
    draft.value.response_style = mode
    draft.value.response_profile.style = mode
  }
})

const tempCustomized = computed(() => draft.value?.response_profile?.temperature != null)
const tempValue = computed({
  get: () => draft.value?.response_profile?.temperature ?? GLOBAL_TEMP,
  set: (v: any) => { if (draft.value?.response_profile) draft.value.response_profile.temperature = Math.round(Number(v) * 10) / 10 },
})
const tempHint = computed(() => {
  const v = draft.value?.response_profile?.temperature
  if (v == null) return { label: '跟随全局', color: 'default', text: `全局默认 ${GLOBAL_TEMP}` }
  if (v <= 0.3) return { label: '稳定', color: 'blue', text: '同类问题答案一致，适合报价核对' }
  if (v <= 0.8) return { label: '适中', color: 'green', text: '回复自然（全局默认档）' }
  return { label: '发散', color: 'orange', text: '表述多变，慎用于严谨场景' }
})

const tokenCustomized = computed(() => draft.value?.response_profile?.max_tokens != null)
const tokenValue = computed({
  get: () => draft.value?.response_profile?.max_tokens ?? GLOBAL_TOKENS,
  set: (v: any) => { if (draft.value?.response_profile) draft.value.response_profile.max_tokens = Number(v) },
})
const tokenHint = computed(() => {
  const v = draft.value?.response_profile?.max_tokens
  if (v == null) return { label: '跟随全局', color: 'default', text: `全局默认 ${GLOBAL_TOKENS}` }
  if (v <= 6000) return { label: '常规', color: 'blue', text: '日常对话够用，长方案或截断' }
  if (v <= 10000) return { label: '长文', color: 'green', text: '详细方案与报告（全局默认档）' }
  return { label: '超长', color: 'orange', text: '极长输出，token 成本上升' }
})

function defaultDraft(source: any = {}) {
  return {
    role_key: source.role_key || '',
    name: source.name || source.role_key || '',
    avatar_url: source.avatar_url || '',
    pet_model: source.pet_model || 'koharu',
    color: source.color || '#1677ff',
    enabled: source.enabled ?? true,
    system_prompt: source.system_prompt || '',
    opening_message: source.opening_message || '',
    response_style: source.response_style || source.response_profile?.style || 'detailed',
    response_profile: {
      style: source.response_profile?.style || source.response_style || 'detailed',
      style_mode: source.response_profile?.style_mode
        || (source.response_profile?.style_prompt?.trim() ? 'custom' : (source.response_profile?.style || source.response_style || 'detailed')),
      max_tokens: source.response_profile?.max_tokens ?? null,
      temperature: source.response_profile?.temperature ?? null,
      style_prompt: source.response_profile?.style_prompt || '',
    },
    model_override: source.model_override || null,
    tool_ids: Array.isArray(source.tool_ids) ? [...source.tool_ids] : [],
    data_sources: Array.isArray(source.data_sources) ? [...source.data_sources] : [],
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
    memory_policy: {
      enabled: source.memory_policy?.enabled ?? true,
      auto_memory: source.memory_policy?.auto_memory ?? true,
    },
    skills: Array.isArray(source.skills)
      ? source.skills.map((item: any) => (typeof item === 'string' ? item : item?.key)).filter(Boolean)
      : [],
  }
}

function selectColleague(roleKey: string) {
  selectedRoleKey.value = roleKey
}

function openEditorFor(roleKey: string) {
  selectColleague(roleKey)
  editorOpen.value = true
}

watch(
  selectedRoleKey,
  (roleKey) => {
    const colleague = props.colleagues.find((c) => c.role_key === roleKey)
    draft.value = colleague ? defaultDraft(colleague) : null
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
    memorySummary.value = { total: 0, pinned: 0, byType: [] }
    return
  }
  try {
    const data = await officeApi.listColleagueMemories(roleKey, { limit: 200 })
    const items = Array.isArray(data.memories) ? data.memories : []
    const typeCounts = new Map<string, number>()
    for (const item of items) {
      const type = String(item?.type || 'business_fact')
      typeCounts.set(type, (typeCounts.get(type) || 0) + 1)
    }
    memorySummary.value = {
      total: Number(data.total ?? items.length),
      pinned: items.filter((item) => !!item?.pinned).length,
      byType: [...typeCounts.entries()].map(([type, count]) => ({ type, count })),
    }
  } catch {
    memorySummary.value = { total: 0, pinned: 0, byType: [] }
  }
}

function resetMemoryForm() {
  editingMemoryId.value = null
  memoryEditorOpen.value = false
  memoryForm.value = { type: 'business_fact', content: '', pinned: false }
}

async function loadMemories() {
  if (!draft.value?.role_key) return
  memoryLoading.value = true
  try {
    const data = await officeApi.listColleagueMemories(draft.value.role_key, {
      keyword: memoryKeyword.value.trim() || undefined,
      limit: 200,
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
  editingMemoryId.value = null
  memoryForm.value = { type: 'business_fact', content: '', pinned: false }
  memoryEditorOpen.value = true
}

function editMemory(record: OfficeColleagueMemory) {
  editingMemoryId.value = Number(record.id)
  memoryForm.value = {
    type: String(record.type || 'business_fact'),
    content: String(record.content || ''),
    pinned: !!record.pinned,
  }
  memoryEditorOpen.value = true
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
      await officeApi.updateColleagueMemory(draft.value.role_key, editingMemoryId.value, {
        type: memoryForm.value.type,
        content,
        pinned: memoryForm.value.pinned,
      })
      message.success('已更新记忆')
    } else {
      await officeApi.createColleagueMemory(draft.value.role_key, {
        type: memoryForm.value.type,
        content,
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

async function toggleMemoryPinned(record: OfficeColleagueMemory) {
  if (!draft.value?.role_key) return
  try {
    await officeApi.updateColleagueMemory(draft.value.role_key, Number(record.id), { pinned: !record.pinned })
    record.pinned = !record.pinned
    await loadMemorySummary()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '更新置顶失败')
  }
}

async function deleteMemory(record: OfficeColleagueMemory) {
  if (!draft.value?.role_key) return
  try {
    await officeApi.deleteColleagueMemory(draft.value.role_key, Number(record.id))
    message.success('已删除记忆')
    await loadMemories()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '删除记忆失败')
  }
}

async function clearMemories() {
  if (!draft.value?.role_key) return
  try {
    await officeApi.clearColleagueMemories(draft.value.role_key)
    message.success('已清空该员工长期记忆')
    memories.value = []
    await loadMemorySummary()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '清空记忆失败')
  }
}

function formatMemoryTime(value?: string) {
  if (!value) return ''
  return new Date(value).toLocaleString()
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
  if (draft.value.response_profile?.style_mode === 'custom' && !draft.value.response_profile.style_prompt?.trim()) {
    message.warning('已选择自定义风格，请填写自定义风格提示词')
    return
  }
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
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.em-cards-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.em-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  min-height: 0;
  overflow: auto;
  padding: 2px 2px 18px;
  align-content: start;
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

.em-param-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.em-param-head .em-param-model {
  flex: 1;
  max-width: 240px;
}

.em-param-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 20px;
}

.em-param-grid .em-slider-field {
  margin-top: 8px;
}

.em-param-note {
  margin-top: 10px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  opacity: 0.85;
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

.em-access-panel {
  margin-top: 14px;
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

.em-identity-cols {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 16px;
  align-items: start;
}
.em-identity-left { min-width: 0; }
.em-identity-right { display: flex; flex-direction: column; gap: 10px; }
.em-identity-right .em-field { margin: 0; }
.em-pet-preview { width: 100%; height: 240px; }
.em-pet-select-dropdown { z-index: 3000 !important; }
@media (max-width: 1100px) {
  .em-identity-cols { grid-template-columns: 1fr; }
  .em-identity-right { order: 2; }
}

.em-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.em-slider-field {
  margin-top: 14px;
}

.em-slider-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}

.em-slider-head > span {
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.em-slider-reset {
  color: var(--cpq-accent, #1677ff);
  font-size: 12px;
  cursor: pointer;
}

.em-slider-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--cpq-text-muted);
  font-size: 12px;
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

.em-advanced {
  margin-bottom: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.em-advanced :deep(.ant-collapse-header) {
  color: var(--cpq-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.em-advanced :deep(.ant-collapse-content-box) {
  display: flex;
  flex-direction: column;
  gap: 12px;
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

.em-memory-hint {
  font-weight: 400;
  line-height: 1.5;
}

.em-memory-editor {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.em-memory-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 460px;
  overflow-y: auto;
}

.em-memory-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
}

.em-memory-item.pinned {
  border-color: rgba(250, 173, 20, 0.4);
}

.em-memory-type {
  flex-shrink: 0;
  margin-top: 2px;
}

.em-memory-body {
  flex: 1;
  min-width: 0;
}

.em-memory-content {
  color: var(--cpq-text-primary);
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}

.em-memory-meta {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  color: var(--cpq-text-muted);
  font-size: 11px;
}

.em-memory-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.em-memory-star {
  color: var(--cpq-text-muted);
  font-size: 14px;
}

.em-memory-star.on {
  color: #faad14;
}

.em-memory-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}

:global(.em-editor-modal .ant-modal-content) { max-height: 88vh; display: flex; flex-direction: column; }
:global(.em-editor-modal .ant-modal-body) { max-height: 74vh; overflow: auto; }
:global(.em-editor-modal .em-form) { height: auto; overflow: visible; border: 0; background: transparent; padding: 0; }
</style>

