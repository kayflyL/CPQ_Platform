<template>
  <div class="behavior-editor">
    <div class="be-toolbar">
      <div>
        <h3>行为偏好</h3>
        <p>配置状态文案、颜色、是否点亮屏幕、动画类型，以及状态对应的办公室区域。</p>
      </div>
    </div>

    <div class="be-section">
      <div class="be-section-title">状态样式</div>
      <div v-for="(meta, status) in draft.status_meta" :key="status" class="be-status-row">
        <span class="be-status-key">{{ status }}</span>
        <a-input v-model:value="meta.label" class="be-label-input" />
        <input v-model="meta.color" type="color" class="tm-color-input" />
        <label class="be-check">
          <a-switch v-model:checked="meta.monitor_active" size="small" />
          点亮屏幕
        </label>
        <a-input-number v-model:value="meta.indicator_opacity" :min="0" :max="1" :step="0.05" class="be-opacity-input" />
        <a-select v-model:value="meta.animation" class="be-animation-input">
          <a-select-option v-for="item in animationOptions" :key="item.value" :value="item.value">
            {{ item.label }}
          </a-select-option>
        </a-select>
      </div>
    </div>

    <div class="be-section">
      <div class="be-section-title">状态 → 区域</div>
      <div v-for="(_, status) in draftStatusZoneMap" :key="status" class="be-zone-row">
        <span class="be-status-key">{{ status }}</span>
        <a-select v-model:value="draftStatusZoneMap[status]" class="be-zone-input">
          <a-select-option v-for="zone in officeZones" :key="zone.id" :value="zone.id">
            {{ zone.label || zone.id }}
          </a-select-option>
        </a-select>
      </div>
    </div>

    <div class="be-section">
      <div class="be-section-title">协作规则</div>
      <div v-for="(rule, index) in draft.collaboration_rules" :key="index" class="be-rule-row">
        <a-input v-model:value="rule.when" class="be-rule-when" placeholder="when" />
        <a-input-number v-model:value="rule.min_members" :min="1" class="be-rule-number" />
        <a-select v-model:value="rule.zone" class="be-zone-input">
          <a-select-option v-for="zone in officeZones" :key="zone.id" :value="zone.id">
            {{ zone.label || zone.id }}
          </a-select-option>
        </a-select>
        <a-button size="small" danger @click="removeRule(index)">删除</a-button>
      </div>
      <a-button size="small" @click="addRule">添加规则</a-button>
    </div>

    <div class="be-section">
      <div class="be-section-title">自主时钟</div>
      <div class="be-rule-row">
        <label class="be-check">
          <a-switch v-model:checked="autonomous.enabled" size="small" />
          启用
        </label>
        <label class="be-check">
          间隔秒
          <a-input-number v-model:value="autonomous.tick_seconds" :min="5" :max="300" class="be-number-input" />
        </label>
        <label class="be-check">
          时区
          <a-input v-model:value="autonomous.timezone" class="be-zone-input" />
        </label>
      </div>

      <div class="be-subsection">
        <div class="be-subsection-title">空闲触发</div>
        <div class="be-rule-row">
          <label class="be-check">
            <a-switch v-model:checked="autonomous.idle.enabled" size="small" />
            启用
          </label>
          <label class="be-check">
            空闲秒
            <a-input-number v-model:value="autonomous.idle.after_seconds" :min="30" :max="86400" class="be-number-input" />
          </label>
          <label class="be-check">
            状态
            <a-input v-model:value="autonomous.idle.status" class="be-zone-input" />
          </label>
          <label class="be-check">
            意图
            <a-input v-model:value="autonomous.idle.intent" class="be-zone-input" />
          </label>
        </div>
        <div class="be-rule-row">
          <label class="be-check">
            活动
            <a-input v-model:value="autonomous.idle.activity" class="be-zone-input" />
          </label>
          <label class="be-check">
            区域
            <a-select v-model:value="autonomous.idle.zone" class="be-zone-input">
              <a-select-option v-for="zone in officeZones" :key="zone.id" :value="zone.id">
                {{ zone.label || zone.id }}
              </a-select-option>
            </a-select>
          </label>
        </div>
      </div>

      <div class="be-subsection">
        <div class="be-subsection-title">自主活动</div>
        <div class="be-rule-row">
          <label class="be-check">
            <a-switch v-model:checked="autonomous.life.enabled" size="small" />
            启用
          </label>
          <label class="be-check">
            冷却秒
            <a-input-number v-model:value="autonomous.life.cooldown_seconds" :min="10" :max="3600" class="be-number-input" />
          </label>
          <label class="be-check">
            每次最多角色数
            <a-input-number v-model:value="autonomous.life.max_actions_per_tick" :min="1" :max="10" class="be-number-input" />
          </label>
        </div>
        <div class="be-rule-row">
          <label class="be-check">
            <a-switch v-model:checked="autonomous.life.llm_enabled" size="small" />
            LLM 决策
          </label>
          <label class="be-check">
            LLM 最小间隔秒
            <a-input-number v-model:value="autonomous.life.llm_min_interval_seconds" :min="30" :max="86400" class="be-number-input" />
          </label>
          <label class="be-check">
            LLM 超时秒
            <a-input-number v-model:value="autonomous.life.llm_timeout_seconds" :min="3" :max="60" class="be-number-input" />
          </label>
        </div>
        <div class="be-rule-row">
          <label class="be-check">
            <a-switch v-model:checked="autonomous.life.interaction_enabled" size="small" />
            同事互动
          </label>
          <label class="be-check">
            互动冷却秒
            <a-input-number v-model:value="autonomous.life.interaction_cooldown_seconds" :min="60" :max="86400" class="be-number-input" />
          </label>
        </div>
        <div class="be-rule-row">
          <label class="be-check">
            允许区域
            <a-select v-model:value="autonomous.life.allowed_zones" mode="multiple" class="be-zone-input">
              <a-select-option v-for="zone in officeZones" :key="zone.id" :value="zone.id">
                {{ zone.label || zone.id }}
              </a-select-option>
            </a-select>
          </label>
        </div>
        <div class="be-rule-row">
          <label class="be-check">
            活跃状态（避开）
            <a-select v-model:value="autonomous.life.active_statuses" mode="tags" class="be-zone-input" placeholder="如 working, meeting" />
          </label>
        </div>
        <div class="be-subsection-title">兜底动作</div>
        <div v-for="(rule, index) in autonomous.life.fallback_actions" :key="index" class="be-schedule-row">
          <a-input v-model:value="rule.status" class="be-schedule-short" placeholder="状态" />
          <a-input v-model:value="rule.intent" class="be-schedule-short" placeholder="意图" />
          <a-input v-model:value="rule.activity" class="be-schedule-activity" placeholder="活动" />
          <a-select v-model:value="rule.zone" class="be-zone-input">
            <a-select-option v-for="zone in officeZones" :key="zone.id" :value="zone.id">
              {{ zone.label || zone.id }}
            </a-select-option>
          </a-select>
          <a-button size="small" danger @click="removeLifeAction(index)">删除</a-button>
        </div>
        <a-button size="small" @click="addLifeAction">添加兜底动作</a-button>
      </div>

      <div class="be-subsection">
        <div class="be-subsection-title">定时规则</div>
        <div v-for="(rule, index) in autonomous.schedule_rules" :key="index" class="be-schedule-row">
          <a-input v-model:value="rule.time" class="be-schedule-time" placeholder="HH:MM" />
          <a-input v-model:value="rule.status" class="be-schedule-short" placeholder="状态" />
          <a-input v-model:value="rule.intent" class="be-schedule-short" placeholder="意图" />
          <a-input v-model:value="rule.activity" class="be-schedule-activity" placeholder="活动" />
          <a-select v-model:value="rule.zone" class="be-zone-input">
            <a-select-option v-for="zone in officeZones" :key="zone.id" :value="zone.id">
              {{ zone.label || zone.id }}
            </a-select-option>
          </a-select>
          <a-button size="small" danger @click="removeScheduleRule(index)">删除</a-button>
        </div>
        <a-button size="small" @click="addScheduleRule">添加定时规则</a-button>
      </div>
    </div>

    <div class="be-section">
      <div class="be-section-title">Brain / LLM 自然互动</div>
      <div class="be-rule-row">
        <label class="be-check">
          <a-switch v-model:checked="brain.enabled" size="small" />
          启用会议摘要与任务分配
        </label>
        <label class="be-check">
          模型覆盖
          <a-input v-model:value="brain.model_override" class="be-zone-input" placeholder="留空使用默认模型" />
        </label>
        <label class="be-check">
          重试次数
          <a-input-number v-model:value="brain.max_attempts" :min="1" :max="3" class="be-number-input" />
        </label>
      </div>
      <div class="be-rule-row">
        <label class="be-check">
          <a-switch v-model:checked="brain.generate_summary" size="small" />
          生成摘要
        </label>
        <label class="be-check">
          <a-switch v-model:checked="brain.generate_assignments" size="small" />
          生成任务分配
        </label>
        <label class="be-check">
          <a-switch v-model:checked="brain.generate_conclusion" size="small" />
          生成结论
        </label>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { officeApi, type BehaviorConfig, type OfficeConfig } from '@/api/office'

const props = defineProps<{
  behaviorConfig?: BehaviorConfig
  officeConfig?: OfficeConfig
}>()
const emit = defineEmits<{ saved: [] }>()

const saving = ref(false)
const draft = ref<BehaviorConfig>({ status_meta: {}, collaboration_rules: [] })
const draftStatusZoneMap = ref<Record<string, string>>({})
const autonomous = ref<NonNullable<BehaviorConfig['autonomous']>>(defaultAutonomous())
const brain = ref<NonNullable<BehaviorConfig['brain']>>(defaultBrain())
const mission = ref<NonNullable<BehaviorConfig['mission']>>(defaultMission())

const animationOptions = [
  { value: 'idle', label: '空闲' },
  { value: 'working', label: '工作' },
  { value: 'waiting', label: '等待' },
  { value: 'done', label: '完成' },
  { value: 'error', label: '异常' },
  { value: 'meeting', label: '协作' },
]

const officeZones = computed(() => props.officeConfig?.zones || [])

function defaultBrain(): NonNullable<BehaviorConfig['brain']> {
  return {
    enabled: false,
    model_override: '',
    max_attempts: 1,
    generate_summary: true,
    generate_assignments: true,
    generate_conclusion: true,
  }
}

function normalizeBrain(value?: BehaviorConfig['brain']): NonNullable<BehaviorConfig['brain']> {
  return { ...defaultBrain(), ...(value || {}) }
}
function defaultMission(): NonNullable<BehaviorConfig['mission']> {
  return {
    enabled: true,
    owner_role_key: 'assistant',
    max_steps: 8,
    max_iterations: 4,
    route_delay_seconds: 1.2,
    work_delay_seconds: 2.5,
    done_delay_seconds: 0.8,
    default_intent: 'work',
    assignment_action_map: {},
    collaboration: {
      enabled: true,
      zone: 'meeting_room',
      status: 'meeting',
      intent: 'collaborate',
      activity: '与协作对象讨论任务',
      keywords: [],
      max_participants: 4,
    },
  }
}

function normalizeMission(value?: BehaviorConfig['mission']): NonNullable<BehaviorConfig['mission']> {
  const fallback = defaultMission()
  if (!value) return fallback
  return {
    ...fallback,
    ...value,
    assignment_action_map: value.assignment_action_map || {},
    collaboration: { ...fallback.collaboration, ...(value.collaboration || {}) },
  }
}

function defaultAutonomous(): NonNullable<BehaviorConfig['autonomous']> {
  return {
    enabled: true,
    tick_seconds: 10,
    timezone: 'Asia/Shanghai',
    life: {
      enabled: true,
      max_actions_per_tick: 1,
      cooldown_seconds: 20,
      llm_enabled: true,
      llm_min_interval_seconds: 180,
      llm_timeout_seconds: 12,
      interaction_enabled: true,
      interaction_cooldown_seconds: 300,
      allowed_zones: ['desk_zone', 'meeting_room', 'public_zone'],
      active_statuses: ['working', 'meeting', 'waiting_input', 'error'],
      fallback_actions: [
        { status: 'working', intent: 'work', zone: 'desk_zone', activity: '整理方案资料', message: '' },
        { status: 'thinking', intent: 'review', zone: 'desk_zone', activity: '复盘近期商机', message: '' },
        { status: 'working', intent: 'work', zone: 'desk_zone', activity: '检查待办任务', message: '' },
        { status: 'public', intent: 'move', zone: 'public_zone', activity: '去公共区稍作休息', message: '' },
      ],
      interaction_action: {
        status: 'meeting',
        intent: 'discuss',
        zone: 'meeting_room',
        activity: '找同事简短沟通',
        message: '一起去会议室碰一下。',
      },
    },
    idle: {
      enabled: true,
      after_seconds: 600,
      status: 'thinking',
      intent: 'review_pending_tasks',
      activity: '自主检查待办',
      zone: 'desk_zone',
    },
    schedule_rules: [],
  }
}

function normalizeAutonomous(value?: BehaviorConfig['autonomous']): NonNullable<BehaviorConfig['autonomous']> {
  const fallback = defaultAutonomous()
  if (!value) return fallback
  return {
    ...fallback,
    ...value,
    life: { ...fallback.life, ...(value.life || {}) },
    idle: { ...fallback.idle, ...(value.idle || {}) },
    schedule_rules: Array.isArray(value.schedule_rules) ? value.schedule_rules : [],
  }
}

function cloneBehavior(value?: BehaviorConfig): BehaviorConfig {
  if (!value) return { status_meta: {}, collaboration_rules: [] }
  return JSON.parse(JSON.stringify(value))
}

function syncDraft() {
  const next = cloneBehavior(props.behaviorConfig)
  next.status_meta = next.status_meta || {}
  next.collaboration_rules = Array.isArray(next.collaboration_rules) ? next.collaboration_rules : []
  draft.value = next
  autonomous.value = normalizeAutonomous(next.autonomous)
  brain.value = normalizeBrain(next.brain)
  mission.value = normalizeMission(next.mission)

  draftStatusZoneMap.value = { ...(props.officeConfig?.status_zone_map || {}) }
}

watch(() => [props.behaviorConfig, props.officeConfig], syncDraft, { deep: true, immediate: true })

function addRule() {
  if (!draft.value.collaboration_rules) draft.value.collaboration_rules = []
  draft.value.collaboration_rules.push({ when: 'same_thread_id', min_members: 2, zone: officeZones.value[0]?.id || 'meeting_room' })
}

function removeRule(index: number) {
  draft.value.collaboration_rules?.splice(index, 1)
}

function addScheduleRule() {
  autonomous.value.schedule_rules.push({
    id: `schedule_${Date.now()}`,
    time: '09:00',
    status: 'meeting',
    intent: 'morning_sync',
    activity: '参加晨会同步',
    zone: officeZones.value[0]?.id || 'meeting_room',
    roles: [],
  })
}

function removeScheduleRule(index: number) {
  autonomous.value.schedule_rules.splice(index, 1)
}

function addLifeAction() {
  autonomous.value.life.fallback_actions.push({
    status: 'thinking',
    intent: 'review',
    zone: officeZones.value[0]?.id || 'desk_zone',
    activity: '自主处理工作',
    message: '',
  })
}

function removeLifeAction(index: number) {
  autonomous.value.life.fallback_actions.splice(index, 1)
}

async function save() {
  saving.value = true
  try {
    await officeApi.updateBehavior({
      ...(draft.value || {}),
      status_meta: draft.value.status_meta,
      collaboration_rules: draft.value.collaboration_rules,
      autonomous: autonomous.value,
      brain: brain.value,
      mission: mission.value,

    })
    await officeApi.updateLayout({
      office: {
        ...(props.officeConfig || {}),
        status_zone_map: draftStatusZoneMap.value,
      },
    })
    message.success('行为偏好已保存')
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '行为偏好保存失败')
  } finally {
    saving.value = false
  }
}
defineExpose({ save })
</script>

<style scoped>

.behavior-editor {
  padding: 16px;
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.be-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.be-toolbar h3 {
  margin: 0;
  font-size: 18px;
}

.be-toolbar p {
  margin: 4px 0 0;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.be-section {
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  padding: 12px;
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.04));
}

.be-section-title {
  margin-bottom: 10px;
  color: var(--cpq-text-secondary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.be-status-row,
.be-zone-row,
.be-rule-row {
  display: grid;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.be-status-row {
  grid-template-columns: 120px minmax(120px, 1fr) 46px 110px 80px 130px;
}

.be-zone-row {
  grid-template-columns: 160px 1fr;
}

.be-rule-row {
  grid-template-columns: minmax(160px, 1fr) 90px minmax(140px, 1fr) 56px;
}

.be-status-key {
  color: var(--cpq-text-secondary);
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.be-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.be-opacity-input,
.be-animation-input,
.be-zone-input,
.be-number-input {
  width: 100%;
}

.be-subsection {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

.be-subsection-title {
  margin-bottom: 8px;
  color: var(--cpq-text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.be-schedule-row {
  display: grid;
  grid-template-columns: 72px 110px 150px minmax(160px, 1fr) minmax(140px, 1fr) 56px;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.be-schedule-time,
.be-schedule-short,
.be-schedule-activity {
  width: 100%;
}
</style>
