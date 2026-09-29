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
      centered
      width="min(94vw, 1000px)"
      wrap-class-name="em-editor-modal"
    >
      <template #title>
        <div class="em-modal-title">
          <span class="em-modal-title-text">员工档案</span>
          <a-button size="small" type="primary" class="em-btn-save-top" :loading="saving" @click="save">保存</a-button>
        </div>
      </template>
      <div class="em-form">

      <template v-if="draft">
        <header class="em-cover" :style="{ '--em-accent': draft.color || '#1677ff' }">
          <div class="em-ring">
            <img v-if="draft.avatar_url" :src="draft.avatar_url" alt="" />
            <Live2dPreview v-else :model-key="draft.pet_model" bg-color="transparent" />
          </div>
          <a-input v-model:value="draft.name" class="em-name-input" :bordered="false" placeholder="员工名称" />
          <div class="em-role-line"><span class="em-role-key">{{ draft.role_key }}</span></div>
          <div class="em-chips">
            <button type="button" class="em-chip" :class="{ on: draft.enabled }" @click="draft.enabled = !draft.enabled">
              <span class="em-chip-dot"></span>{{ draft.enabled ? '在职' : '停用' }}
            </button>
            <button type="button" class="em-chip" :class="{ on: draft.dispatchable }" @click="draft.dispatchable = !draft.dispatchable">
              <span class="em-chip-dot"></span>可被总助分派
            </button>
            <a-tooltip title="在『员工 → 访问权限』页签修改">
              <span class="em-chip is-static" :class="{ on: priceOn }">
                <span class="em-chip-dot"></span>{{ priceOn ? '价格可见' : '价格不可见' }}
              </span>
            </a-tooltip>
          </div>
          <a-textarea
            v-model:value="draft.opening_message"
            class="em-quote"
            :auto-size="{ minRows: 1, maxRows: 3 }"
            placeholder="开场白（个人陈述）：这位同事开口的第一句"
          />
          <div class="em-blank">
            <span>主题色</span>
            <input v-model="draft.color" type="color" class="em-color" />
          </div>
          <div class="em-blank">
            <span>形象</span>
            <a-select v-model:value="draft.pet_model" class="em-blank-select" :bordered="false" dropdown-class-name="em-pet-select-dropdown" style="width: 100%">
              <a-select-option v-for="m in PET_MODEL_CATALOG" :key="m.key" :value="m.key">{{ m.label }}</a-select-option>
            </a-select>
          </div>
          <div class="em-blank">
            <span>头像 URL</span>
            <a-input v-model:value="draft.avatar_url" class="em-blank-input" :bordered="false" placeholder="https://…，留空显示形象" />
          </div>
          <div class="em-blank">
            <span>3D 模型</span>
            <a-input v-model:value="draft.model_url" class="em-blank-input" :bordered="false" placeholder="/models/…/*.vrm，留空自动轮换" />
          </div>
        </header>

        <section class="em-sec">
          <h3 class="em-sec-title">人格与指令</h3>
          <p class="em-sec-sub">这位同事的大脑——提示词决定ta是谁，风格决定ta怎么说话</p>
          <label class="em-field">
            <span>System Prompt / 人格</span>
            <a-textarea v-model:value="draft.system_prompt" :auto-size="{ minRows: 5, maxRows: 12 }" placeholder="定义这位同事的性格、职责边界和说话方式" />
          </label>
          <div class="em-field">
            <span>回复风格</span>
            <div class="em-pills">
              <button type="button" class="em-pill" :class="{ on: draft.response_profile.style_mode === 'brief' }" @click="draft.response_profile.style_mode = 'brief'">简洁</button>
              <button type="button" class="em-pill" :class="{ on: draft.response_profile.style_mode === 'detailed' }" @click="draft.response_profile.style_mode = 'detailed'">详细</button>
              <button type="button" class="em-pill" :class="{ on: draft.response_profile.style_mode === 'custom' }" @click="draft.response_profile.style_mode = 'custom'">自定义</button>
            </div>
          </div>
          <label v-if="draft.response_profile.style_mode === 'custom'" class="em-field">
            <span>自定义风格提示词</span>
            <a-textarea v-model:value="draft.response_profile.style_prompt" :auto-size="{ minRows: 2, maxRows: 4 }" placeholder="例：先给结论再展开，语气活泼，适度使用表情符号 😊" />
          </label>

          <div class="em-param-grid">
            <div>
              <div class="em-param-head">
                <span>温度</span>
                <b class="em-readout">{{ tempValue.toFixed(1) }} · {{ tempHint.label }}</b>
                <button v-if="tempCustomized" type="button" class="em-reset-btn" @click="draft.response_profile.temperature = null">恢复跟随全局</button>
              </div>
              <a-slider
                v-model:value="tempValue"
                class="em-slider"
                :min="0"
                :max="1.5"
                :step="0.1"
                :tip-formatter="(v: number) => v.toFixed(1)"
              />
              <div class="em-param-hint">{{ tempHint.text }}</div>
            </div>
            <div>
              <div class="em-param-head">
                <span>推理档位</span>
                <b class="em-readout">{{ reasonHint.label }}</b>
              </div>
              <div class="em-pills">
                <button type="button" class="em-pill" :class="{ on: reasonTier === 'default' }" @click="reasonTier = 'default'">跟随全局</button>
                <button type="button" class="em-pill" :class="{ on: reasonTier === 'low' }" @click="reasonTier = 'low'">低（快）</button>
                <button type="button" class="em-pill" :class="{ on: reasonTier === 'medium' }" @click="reasonTier = 'medium'">中</button>
                <button type="button" class="em-pill" :class="{ on: reasonTier === 'high' }" @click="reasonTier = 'high'">高（深）</button>
              </div>
              <div class="em-param-hint">{{ reasonHint.text }}</div>
            </div>
            <div>
              <div class="em-param-head">
                <span>模型覆盖</span>
                <b class="em-readout">{{ draft.model_override ? '本员工专属' : '跟随全局' }}</b>
                <button v-if="draft.model_override" type="button" class="em-reset-btn" @click="draft.model_override = null">清除</button>
              </div>
              <a-input v-model:value="draft.model_override" placeholder="模型 id，留空用全局默认" allow-clear />
              <div class="em-param-hint">仅本员工的对话走此模型</div>
            </div>
          </div>
          <div class="em-param-note">工作流业务问答固定低温 0.2，不受以上参数影响</div>
        </section>

        <section class="em-sec">
          <h3 class="em-sec-title">能力</h3>
          <p class="em-sec-sub">绑定工作流发起任务流；query_data 可读表 = 工具自有白名单</p>
          <label class="em-field">
            <span>工作流</span>
            <a-select
              v-model:value="draft.workflows"
              class="em-cloud"
              mode="multiple"
              :options="workflowOptions"
              placeholder="点此添加工作流"
              style="width: 100%"
            />
          </label>
          <label class="em-field">
            <span>可用工具</span>
            <a-select
              v-model:value="draft.tool_ids"
              class="em-cloud"
              mode="multiple"
              :options="toolOptions"
              placeholder="点此添加工具"
              style="width: 100%"
            />
          </label>
        </section>

        <section class="em-sec">
          <h3 class="em-sec-title">记忆</h3>
          <p class="em-sec-sub">公共域在此维护（全员共享注入）；对话写入的记忆归用户私有域（仅本人可见），上下各 100 条</p>
          <div class="em-mem-row">
            <a-switch v-model:checked="draft.memory_policy.enabled" />
            <span class="em-mem-label">启用长期记忆</span>
            <span class="em-mem-stats">
              <a-tag>共 {{ memorySummary.total }} 条</a-tag>
              <a-tag color="gold">置顶 {{ memorySummary.pinned }}</a-tag>
              <a-tag v-for="item in memorySummary.byType" :key="item.type" :color="typeMeta(item.type).color">
                {{ typeMeta(item.type).label }} {{ item.count }}
              </a-tag>
            </span>
          </div>
          <div class="em-mem-row">
            <a-switch v-model:checked="draft.memory_policy.auto_memory" />
            <span class="em-mem-label">对话后自动学习</span>
          </div>
          <div class="em-mem-links">
            <a-button type="link" size="small" @click="openMemories">管理记忆 →</a-button>
            <a-button type="link" size="small" @click="openThreads">会话管理 →</a-button>
          </div>
        </section>

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
          <a-button class="em-btn-danger" danger type="text" :loading="saving" @click="confirmDelete">删除员工</a-button>
          <a-button type="primary" class="em-btn-save" :loading="saving" @click="save">保存</a-button>
        </div>
      </template>
      <div v-else class="em-empty">选择左侧员工，或新建一位 AI 同事</div>
      </div>
    </a-modal>

    <a-modal v-model:open="memoryOpen" :title="`长期记忆（公共域）：${draft?.name || draft?.role_key || ''}`" :footer="null" width="min(94vw, 720px)">
      <p class="em-mem-scope-note">此处维护<b>公共域</b>记忆（全员共享）；对话中同事自主写入的记忆归属对话用户的<b>私有域</b>（仅本人可见），不在此列表。</p>
      <div class="em-memory-toolbar">
        <a-input-search
          v-model:value="memoryKeyword"
          placeholder="搜索记忆内容"
          allow-clear
          style="width: 240px"
          @search="loadMemories"
        />
        <a-checkbox v-model:checked="memoryShowRetired" @change="loadMemories">含已失效</a-checkbox>
        <a-button size="small" @click="loadMemories">刷新</a-button>
        <a-popconfirm title="让该同事全量复查自己的记忆（去重/归并/清一次性条目）？" @confirm="consolidateMemories">
          <a-button size="small" :loading="memoryConsolidating">整理</a-button>
        </a-popconfirm>
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
          <div v-for="item in memories" :key="item.id" class="em-memory-item" :class="{ pinned: item.pinned, retired: !!item.retired_at }">
            <a-tag :color="typeMeta(item.type).color" class="em-memory-type">{{ item.type_label || typeMeta(item.type).label }}</a-tag>
            <div class="em-memory-body">
              <div class="em-memory-content">{{ item.content }}</div>
              <div class="em-memory-meta">
                <span>{{ memoryViaLabel(item) }}</span>
                <span v-if="item.retired_at" class="em-memory-retired-mark">
                  已失效{{ item.superseded_by ? `（被 #${item.superseded_by} 取代）` : '' }}
                </span>
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
          <a-empty v-if="!memories.length && !memoryLoading" description="暂无公共域记忆。同事在对话中自主记住的归用户私有域（不在此列）；全员共享的事实点「新建记忆」添加。" />
        </div>
      </a-spin>
    </a-modal>

    <a-modal
      v-model:open="threadsOpen"
      :title="`会话管理：${draft?.name || draft?.role_key || ''}`"
      :footer="null"
      width="min(94vw, 880px)"
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

    <a-modal v-model:open="threadMessagesOpen" title="会话消息" :footer="null" width="min(94vw, 640px)">
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
      width="min(94vw, 520px)"
      :confirm-loading="renameThreadSaving"
      @ok="saveRenameThread"
    >
      <a-input v-model:value="renameThreadForm.title" placeholder="输入会话标题" allow-clear />
    </a-modal>

    <a-modal v-model:open="createOpen" title="新建 AI 同事" :footer="null" width="min(94vw, 520px)">
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
const memoryShowRetired = ref(false)
const memoryConsolidating = ref(false)
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
const priceOn = computed(() =>
  props.colleagues.find((c: any) => c?.role_key === draft.value?.role_key)?.price_access === true)
const toolOptions = computed(() => tools.value.map((tool) => ({ value: tool.name, label: tool.name })))
const workflowOptions = computed(() =>
  skills.value
    .filter((skill) => skill?.type === 'workflow')
    .map((skill) => ({ value: skill.key, label: skill.name || skill.key })),
)
const normalThreads = computed(() => allThreads.value.filter((t) => !t.deleted_at))
const deletedThreads = computed(() => allThreads.value.filter((t) => t.deleted_at))

const GLOBAL_TEMP = 0.7
const GLOBAL_TOKENS = 16000
// 推理档位 = 思考强度(reasoning_effort) + 输出预算(max_tokens) 一个旋钮，避免两处可设项打架。
const REASON_TIERS: Record<string, { reasoning_effort: string; max_tokens: number; label: string; color: string; text: string }> = {
  low:    { reasoning_effort: 'low',    max_tokens: 16000, label: '低档', color: 'blue',   text: '思考档 low · 输出 16k，快速，常规选型' },
  medium: { reasoning_effort: 'medium', max_tokens: 24000, label: '中档', color: 'green',  text: '思考档 medium · 输出 24k，复杂配置更稳' },
  high:   { reasoning_effort: 'high',   max_tokens: 32000, label: '高档', color: 'orange', text: '思考档 high · 输出 32k，深度推理，耗时与成本上升' },
}

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

const reasonTier = computed({
  get: () => {
    const p = draft.value?.response_profile
    if (!p) return 'default'
    const eff = p.reasoning_effort
    if (eff && REASON_TIERS[eff]) return eff
    const mt = p.max_tokens
    if (mt == null) return 'default'
    if (mt >= 32000) return 'high'
    if (mt >= 24000) return 'medium'
    return 'low'
  },
  set: (v: any) => {
    if (!draft.value?.response_profile) return
    if (v === 'default') {
      draft.value.response_profile.reasoning_effort = null
      draft.value.response_profile.max_tokens = null
      return
    }
    const t = REASON_TIERS[v]
    if (t) {
      draft.value.response_profile.reasoning_effort = t.reasoning_effort
      draft.value.response_profile.max_tokens = t.max_tokens
    }
  },
})
const reasonHint = computed(() => {
  const eff = draft.value?.response_profile?.reasoning_effort
  const t = eff && REASON_TIERS[eff] ? REASON_TIERS[eff] : null
  if (!t) return { label: '跟随全局', color: 'default', text: `全局默认 low / ${GLOBAL_TOKENS}` }
  return t
})

function defaultDraft(source: any = {}) {
  return {
    role_key: source.role_key || '',
    name: source.name || source.role_key || '',
    avatar_url: source.avatar_url || '',
    pet_model: source.pet_model || 'koharu',
    model_url: source.model_url || '',
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
      reasoning_effort: source.response_profile?.reasoning_effort ?? null,
      temperature: source.response_profile?.temperature ?? null,
      style_prompt: source.response_profile?.style_prompt || '',
    },
    model_override: source.model_override || null,
    tool_ids: Array.isArray(source.tool_ids) ? [...source.tool_ids] : [],
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
    workflows: Array.isArray(source.workflows)
      ? source.workflows.map((item: any) => (typeof item === 'string' ? item : item?.key)).filter(Boolean)
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
    const res = await assistantApi.tools.catalog()
    tools.value = res.tools
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
      include_retired: memoryShowRetired.value || undefined,
    })
    memories.value = Array.isArray(data.memories) ? data.memories : []
    await loadMemorySummary()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '长期记忆加载失败')
  } finally {
    memoryLoading.value = false
  }
}

function memoryViaLabel(item: OfficeColleagueMemory) {
  if (item.source === 'manual') return '手动'
  try {
    const via = JSON.parse(item.provenance || '{}')?.via
    if (via === 'memory_tool') return '对话记忆'
    if (via === 'consolidation') return '整理归并'
  } catch { /* provenance 非法时走历史兜底 */ }
  return '历史'
}

async function consolidateMemories() {
  if (!draft.value?.role_key) return
  memoryConsolidating.value = true
  try {
    const report = await officeApi.consolidateColleagueMemories(draft.value.role_key)
    message.success(`整理完成：${report.applied} 项生效${report.skipped?.length ? `，${report.skipped.length} 项提案被守卫拦下` : ''}`)
    await loadMemories()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '整理失败')
  } finally {
    memoryConsolidating.value = false
  }
}

function openMemories() {
  if (!draft.value?.role_key) return
  memoryKeyword.value = ''
  memoryShowRetired.value = false
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
  padding: 2px 2px 4px;
  align-content: start;
}

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

/* 参数三件套同构：标题行(label+读数+重置) / 控件 / 提示，auto-fit 自适应分列 */
.em-param-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 14px 36px;
  align-items: start;
}

.em-param-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.em-param-head > span {
  color: var(--cpq-text-muted);
  font-size: 12px;
  flex: none;
}

.em-param-head .em-readout {
  margin-left: auto;
}

.em-param-hint {
  margin-top: 4px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

/* 「恢复跟随全局/清除」：正规小按钮，不再嵌在提示文字里当链接 */
.em-reset-btn {
  border: none;
  background: transparent;
  padding: 1px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  color: var(--cpq-accent-primary);
  cursor: pointer;
  transition: background var(--cpq-dur-1) var(--cpq-ease-smooth);
}

.em-reset-btn:hover {
  background: var(--cpq-overlay-a10);
}

.em-param-note {
  margin-top: 14px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  opacity: 0.85;
}

.em-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

/* ── 员工档案（简历风封面 + 居中分节）────────────────────────── */

.em-cover {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: -20px -24px 0;          /* 抵消 modal body padding(20px 24px)，色带通到纸边 */
  padding: 26px 24px 18px;
  background: var(--cpq-overlay-a5);
  border-bottom: 1px solid var(--cpq-border-primary);
}

.em-ring {
  width: 148px;
  height: 148px;
  border-radius: 50%;
  border: 4px solid color-mix(in srgb, var(--em-accent, #1677ff) 28%, transparent);
  background: color-mix(in srgb, var(--em-accent, #1677ff) 10%, transparent);
  overflow: hidden;
}

.em-ring img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* Live2dPreview 自带 min-height:220px + 10px 圆角，在 148px 圆环里必须清掉 */
.em-ring :deep(.l2d-preview-box) {
  min-height: 0;
  border-radius: 0;
}

/* Live2D 全身太远 → 放大 1.45 倍裁上半身：锚点定在头顶附近（10%），完整头部+躯干，腿部裁出圆外 */
.em-ring :deep(.l2d-preview-box) canvas {
  transform: scale(1.45);
  transform-origin: 50% 10%;
}

/* 大名字 = 输入框，叠双层错位阴影（参考羡辙简历招牌阴影，色值走 cpq token）。
   a-input 根元素即 input.ant-input（无包裹层），类落在元素自身——自选择器与后代选择器都写上双保险 */
.em-name-input.ant-input,
.em-name-input :deep(input.ant-input) {
  width: min(320px, 92%);
  margin-top: 16px;
  text-align: center;
  font-size: 28px;
  font-weight: 800;
  color: var(--cpq-text-primary);
  text-shadow: 1px 2px 0 color-mix(in srgb, var(--em-accent, #1677ff) 30%, transparent),
    3px 5px 0 color-mix(in srgb, var(--em-accent, #1677ff) 12%, transparent);
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  border-radius: 0 !important;
}

.em-name-input.ant-input::placeholder,
.em-name-input :deep(input.ant-input::placeholder) {
  text-shadow: none;
  font-weight: 400;
}

.em-role-line {
  margin-top: 10px;
}

.em-role-key {
  display: inline-block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  letter-spacing: 1px;
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
  padding: 2px 12px;
  border-radius: 999px;
}

.em-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}

.em-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--cpq-border-primary);
  background: var(--cpq-glass-1-bg, rgba(255, 255, 255, 0.04));
  color: var(--cpq-text-muted);
  font-size: 12px;
  line-height: 1.6;
  cursor: pointer;
  transition: all 0.15s ease;
}

button.em-chip:hover {
  border-color: rgba(22, 119, 255, 0.45);
}

.em-chip.is-static {
  cursor: default;
}

.em-chip-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  opacity: 0.5;
  flex-shrink: 0;
}

.em-chip.on {
  color: var(--cpq-text-primary);
  border-color: rgba(22, 119, 255, 0.4);
  background: rgba(22, 119, 255, 0.1);
}

.em-chip.on .em-chip-dot {
  background: #52c41a;
  opacity: 1;
}

/* 开场白：透明纸面 + 虚线填空。a-textarea(auto-size) 根元素即 textarea，类落在自身——
   旧代码只写 :deep(textarea) 后代选择器从未命中，全局玻璃底色因此透出（用户实测底色显眼的根因） */
.em-quote.ant-input,
.em-quote :deep(textarea.ant-input) {
  width: min(480px, 100%);
  margin-top: 14px;
  padding: 6px 4px;
  border: none !important;
  border-bottom: 1px dashed var(--cpq-overlay-a20) !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  text-align: center;
  color: var(--cpq-text-secondary);
  font-size: 13px;
  font-style: italic;
}

/* 封面填空行：纸面横线填空 */
.em-blank {
  display: flex;
  align-items: center;
  gap: 14px;
  width: min(420px, 100%);
  padding: 7px 2px;
  border-bottom: 1px solid var(--cpq-border-primary);
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth);
}

.em-blank:focus-within {
  border-bottom-color: var(--cpq-glass-border-strong);
}

.em-blank > span {
  min-width: 64px;
  text-align: right;
  font-size: 12.5px;
  color: var(--cpq-text-muted);
  flex: none;
}

.em-blank-input.ant-input,
.em-blank-input :deep(input.ant-input) {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  padding-left: 0;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  border-radius: 0 !important;
}

.em-blank-select :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent;
  padding: 0;
}

.em-pet-select-dropdown { z-index: 3000 !important; }

/* ══ pill 控件语言（回复风格/推理档位）══════════════════════ */
.em-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.em-pill {
  padding: 3px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-family: inherit;
  border: 1px solid var(--cpq-border-primary);
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}

.em-pill:hover {
  color: var(--cpq-accent-primary);
  border-color: rgba(22, 119, 255, 0.45);
}

.em-pill.on {
  color: var(--cpq-accent-primary);
  border-color: rgba(22, 119, 255, 0.4);
  background: var(--cpq-overlay-a10);
  font-weight: 600;
}

/* 滑杆：粗圆轨道（antd 默认细轨 + marks 已去掉） */
.em-slider :deep(.ant-slider-rail) {
  height: 6px;
  border-radius: 3px;
  background: var(--cpq-overlay-a10);
}

.em-slider :deep(.ant-slider-track) {
  height: 6px;
  border-radius: 3px;
  background: var(--cpq-accent-primary);
}

.em-slider :deep(.ant-slider-handle .ant-slider-handle-icon) {
  box-shadow: 0 1px 4px rgba(22, 119, 255, 0.4);
}

/* 滑杆/档位右侧蓝色读数 */
.em-readout {
  color: var(--cpq-accent-primary);
  font-size: 12.5px;
  font-weight: 600;
  font-feature-settings: 'tnum' 1;
}

/* 能力区：select 透明化成 pill 云（选中项=蓝 pill，空态 hover 出虚线框） */
.em-cloud :deep(.ant-select-selector) {
  background: transparent !important;
  border: 1px dashed transparent !important;
  box-shadow: none !important;
  border-radius: var(--cpq-radius-sm) !important;
  padding: 2px 6px !important;
}

.em-cloud:hover :deep(.ant-select-selector),
.em-cloud :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--cpq-border-light) !important;
}

.em-cloud :deep(.ant-select-selection-item) {
  background: var(--cpq-overlay-a10) !important;
  border: 1px solid rgba(22, 119, 255, 0.35) !important;
  color: var(--cpq-accent-primary) !important;
  border-radius: 999px !important;
  padding-inline: 10px !important;
  line-height: 22px !important;
  font-size: 12px;
}

.em-cloud :deep(.ant-select-selection-item-remove) {
  color: inherit;
}

/* 记忆：单行 = 开关 + 文案 + 右侧统计 pill */
.em-mem-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 2px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}

.em-mem-row:last-of-type {
  border-bottom: none;
}

.em-mem-label {
  font-size: 14px;
  color: var(--cpq-text-primary);
}

.em-mem-stats {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.em-mem-links {
  display: flex;
  gap: 8px;
  padding-top: 10px;
}

.em-sec {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 22px 28px 6px;
}

.em-sec + .em-sec,
.em-advanced,
.em-actions {
  border-top: 1px solid var(--cpq-border-secondary, rgba(255, 255, 255, 0.06));
}

.em-sec-title {
  margin: 0;
  text-align: center;
  font-size: 17px;
  font-weight: 800;
  color: var(--cpq-text-primary);
  text-shadow: 1px 2px 0 var(--cpq-overlay-a15);
}

.em-sec-sub {
  margin: -6px 0 2px;
  text-align: center;
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.em-color {
  width: 40px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

@media (max-width: 560px) {
  .em-cover { padding-top: 20px; }
  .em-ring { width: 116px; height: 116px; }
  .em-name-input.ant-input,
  .em-name-input :deep(input) { font-size: 22px; }
  .em-blank > span { min-width: 56px; }
}

.em-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.em-zone-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 90px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.em-advanced {
  padding-top: 12px;
}

.em-advanced :deep(.ant-collapse-header) {
  color: var(--cpq-text-muted);
  font-size: 12px;
  font-weight: 700;
  padding-left: 0;
}

.em-advanced :deep(.ant-collapse-content-box) {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.em-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 28px 10px;
}

.em-btn-danger {
  opacity: 0.75;
}

.em-btn-danger:hover {
  opacity: 1;
}

.em-btn-save {
  min-width: 132px;
  /* #app .ant-btn-primary(ID级)会碾掉渐变，按 portal-sheet 先例用 !important 夺回 */
  background: var(--cpq-accent-gradient) !important;
  border: none !important;
  box-shadow: 0 6px 18px rgba(22, 119, 255, 0.30);
}

.em-btn-save:hover {
  filter: brightness(1.08);
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
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 10px;
  background: var(--cpq-overlay-w3);
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

.em-mem-scope-note {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary, rgba(0, 0, 0, 0.45));
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
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 10px;
  background: var(--cpq-overlay-w3);
}

.em-memory-item.pinned {
  border-color: rgba(250, 173, 20, 0.4);
}

.em-memory-item.retired .em-memory-content {
  color: var(--cpq-text-muted);
  text-decoration: line-through;
  text-decoration-color: color-mix(in srgb, var(--cpq-text-muted) 55%, transparent);
}

.em-memory-retired-mark {
  color: var(--cpq-danger, #cf1322);
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


/* 简历纸：实色纸面（glass-3 磨砂会透底噪）+ 宽度 min(94vw,1000px) 随窗口自适应，高度自然生长（超 92vh 内部滚动） */
:global(.em-editor-modal .ant-modal-content) {
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--cpq-bg-card) !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  border: 1px solid var(--cpq-border-primary) !important;
}

:global(.em-editor-modal .ant-modal-body) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable;
}

/* 标题栏弱化：纸的感觉不需要粗标题，认得出来即可 */
:global(.em-editor-modal .ant-modal-header) {
  background: transparent;
  border-bottom: none;
  text-align: center;
}

:global(.em-editor-modal .ant-modal-title) {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 4px;
  color: var(--cpq-text-muted);
}

/* 标题栏 = 常驻操作栏：保存按钮跟随视口，长表单滚到哪都能存 */
.em-modal-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  /* 右侧净空留给绝对定位的关闭按钮，避免保存按钮与其叠放 */
  padding-right: 40px;
}

.em-modal-title-text {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 4px;
  color: var(--cpq-text-muted);
}

.em-btn-save-top {
  margin-right: 4px;
}
</style>
