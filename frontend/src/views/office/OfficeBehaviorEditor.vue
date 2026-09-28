<template>
  <div class="behavior-editor">
    <!-- ── 全局条 ─────────────────────────────── -->
    <div class="be-global">
      <div class="gb-item">
        <a-switch v-model:checked="auto.enabled" size="small" />
        <span>自主时钟</span>
      </div>
      <div class="gb-item">
        心跳 <a-input-number v-model:value="auto.tick_seconds" :min="5" :max="300" size="small" class="gb-num" />
      </div>
      <div class="gb-item">
        时区
        <a-select v-model:value="tzProxy" :options="TIMEZONES" size="small" class="gb-tz" />
      </div>
      <span class="gb-sep" />
      <div class="gb-item">
        <a-switch v-model:checked="life.enabled" size="small" />
        <span>自主活动</span>
      </div>
      <div class="gb-item">
        <a-switch v-model:checked="life.llm_enabled" size="small" />
        <span>LLM 措辞</span>
      </div>
      <div class="gb-item">
        预算
        <a-slider v-model:value="budgetProxy" :min="0" :max="20" :step="1" :tooltip-open="false" class="gb-slider" />
        <b>{{ life.llm_budget_per_hour ?? 0 }}</b> 次/h
      </div>
      <span class="gb-hint">超限 / 失败 → 自动降级日程模板</span>
    </div>

    <!-- ── 一日作息时间轴 ─────────────────────── -->
    <div class="be-section">
      <div class="be-card-head">
        <div class="be-title">
          一日作息
          <span class="be-sub">拖边缘调时长 · 拖中间整体挪 · 点色块在下方编辑</span>
        </div>
      </div>
      <div class="tl-wrap">
        <div class="swim">
          <div class="swim-row swim-row--head">
            <div class="swim-label swim-label--head" />
            <div class="swim-axis">
              <span v-for="h in 11" :key="h" :style="{ left: ((h - 1) * 10) + '%' }">{{ String(h + 8).padStart(2, '0') }}:00</span>
            </div>
          </div>
          <div v-for="lane in lanes" :key="lane.role" class="swim-row" :class="{ active: lane.role === curRole }">
            <button class="swim-label" :title="lane.name" @click="curRole = lane.role; selKey = ''">
              <i :style="{ background: lane.color }" /><span class="swim-name">{{ lane.name }}</span>
            </button>
            <div class="swim-track">
              <div v-if="lane.role === curRole && nowPct >= 0 && nowPct <= 100" class="nowline" :style="{ left: nowPct + '%' }">
                <span>现在</span>
              </div>
              <div
                v-for="vs in lane.segs"
                :key="vs.key"
                class="seg"
                :class="[statusClass(vs.seg.status), { sel: vs.key === selKey, mini: vs.seg.start && vs.seg.end && toMin(vs.seg.end) - toMin(vs.seg.start) < 30 }]"
                :style="{ left: pctOf(vs.seg.start), width: widthOf(vs.seg) }"
                :title="`${vs.seg.start}–${vs.seg.end} · ${segTitle(vs)} @${zoneLabel(vs.seg.zone)}`"
                @pointerdown="onSegDown($event, vs, lane)"
              >
                <span class="h hl" />
                <span class="t">{{ statusIcon(vs.seg.status) }} {{ segTitle(vs) }}</span>
                <span class="tm">{{ vs.seg.start }}–{{ vs.seg.end }}<template v-if="!vs.shared"> · 个人</template></span>
                <span class="h hr" />
              </div>
              <div v-if="laneTailGap(lane) >= 30" class="add-tail" :style="{ left: laneTailLeft(lane) }" @click="addSegment(lane)">＋ 新增</div>
            </div>
          </div>
        </div>
        <div class="legend">
          <em v-for="(m, key) in STATUS_UI" :key="key" :class="m.cls">{{ m.label }}</em>
        </div>
        <div class="prio-note">⚖ 优先级：<b>任务派单随时打断作息</b>（看板任务 &gt; 日程段 &gt; 空闲）；日程段为任务提供语境（谁 / 在哪 / 刚做什么），任务结束回到当时所在段</div>
      </div>

      <!-- 选中段编辑器 -->
      <div v-if="selectedSeg" class="seg-editor">
        <div class="se-title">
          选中：<b>{{ selectedSeg.seg.start }} – {{ selectedSeg.seg.end }} · {{ segTitle(selectedSeg) }}</b>
          <a-tag :color="selectedSeg.shared ? 'blue' : 'green'" class="se-tag">{{ selectedSeg.shared ? '全员段' : '个人段' }}</a-tag>
          <span class="se-plan">{{ selectedSeg.planLabel }}</span>
        </div>
        <div class="se-grid">
          <div class="fld"><label>活动文案</label>
            <a-input v-model:value="selectedSeg.seg.activity" class="se-wide" placeholder="{name} 去茶水间歇口气（留空=状态默认文案）" />
          </div>
          <div class="fld"><label>状态</label>
            <a-select v-model:value="selectedSeg.seg.status" :options="statusOptions" size="small" class="se-mid" />
          </div>
          <div class="fld"><label>意图</label>
            <a-input v-model:value="selectedSeg.seg.intent" size="small" class="se-mid" placeholder="work" />
          </div>
          <div class="fld"><label>区域</label>
            <a-select v-model:value="selectedSeg.seg.zone" :options="zoneOptions" size="small" class="se-mid" />
          </div>
          <div class="fld"><label>开始</label>
            <a-input v-model:value="selectedSeg.seg.start" size="small" class="se-time" placeholder="09:00" />
          </div>
          <div class="fld"><label>结束</label>
            <a-input v-model:value="selectedSeg.seg.end" size="small" class="se-time" placeholder="09:30" />
          </div>
          <button class="del-seg" @click="removeSegment">删除此段</button>
        </div>
        <div class="se-weekdays">
          生效日：
          <button
            v-for="d in 7"
            :key="d"
            class="wd"
            :class="{ on: planWeekdays.includes(d) }"
            @click="toggleWeekday(d)"
          >{{ DAY_LABELS[d - 1] }}</button>
          <span class="se-plan-hint">作用于该段所属计划（{{ selectedSeg.planLabel }}）</span>
        </div>
      </div>
      <div v-else class="seg-editor se-empty">点选一个色块进行编辑；「＋ 新增」会把个人段排进一天末尾的空档</div>
    </div>

    <!-- ── 智能层 ────────────────────────────── -->
    <div class="be-section">
        <div class="be-section-title">智能层 <span class="be-tag-note">LLM 只产日程与措辞 · 执行走确定性时钟</span></div>

        <div class="smart-row">
          <a-switch v-model:checked="brain.enabled" size="small" />
          <span class="name">会议智能</span>
          <span class="desc">协作后生成摘要 / 任务分配 / 结论</span>
          <a-switch v-model:checked="brain.generate_summary" size="small">
            <template #checkedChildren>摘要</template>
          </a-switch>
          <a-switch v-model:checked="brain.generate_assignments" size="small">
            <template #checkedChildren>分配</template>
          </a-switch>
          <a-switch v-model:checked="brain.generate_conclusion" size="small">
            <template #checkedChildren>结论</template>
          </a-switch>
        </div>
        <div class="smart-row">
          <span class="name">会议模型</span>
          <span class="desc">留空使用默认模型</span>
          <a-input v-model:value="brainModelProxy" size="small" class="se-mid" placeholder="默认模型" />
          重试
          <a-input-number v-model:value="brain.max_attempts" :min="1" :max="3" size="small" class="gb-num" />
        </div>
        <div class="smart-row">
          <a-switch v-model:checked="life.interaction_enabled" size="small" />
          <span class="name">同事互动</span>
          <span class="desc">段内低频找人碰一下</span>
          冷却
          <a-input-number v-model:value="life.interaction_cooldown_seconds" :min="60" :max="86400" size="small" class="gb-num" /> 秒
        </div>
        <div class="smart-row">
          <span class="name">协作联动</span>
          <span class="desc">同一线索 ≥ N 人在线 → 自动移步会议室</span>
        </div>
        <div class="smart-sub" v-for="(rule, i) in collabRules" :key="i">
          <span class="se-plan">同线索</span>
          ≥ <a-input-number v-model:value="rule.min_members" :min="2" size="small" class="gb-num" /> 人
          <a-select v-model:value="rule.zone" :options="zoneOptions" size="small" class="se-mid" />
          冷却 <a-input-number v-model:value="rule.cooldown_seconds" :min="30" size="small" class="gb-num" /> 秒
          <a-button size="small" danger type="text" @click="collabRules.splice(i, 1)">删</a-button>
        </div>
        <a-button size="small" class="se-add" @click="addCollabRule">＋ 添加协作规则</a-button>

        <div class="smart-row mission-row">
          <a-switch v-model:checked="mission.enabled" size="small" />
          <span class="name">任务引擎</span>
          <span class="desc">派单驱动同事执行（优先级高于作息）</span>
        </div>
        <div class="smart-sub">
          责任人
          <a-select v-model:value="missionOwnerProxy" :options="colleagueOptions" size="small" class="se-mid" />
          最多步数 <a-input-number v-model:value="mission.max_steps" :min="1" :max="30" size="small" class="gb-num" />
          最多轮次 <a-input-number v-model:value="mission.max_iterations" :min="1" :max="10" size="small" class="gb-num" />
        </div>
      </div>

    <!-- ── 外观层（折叠） ─────────────────────── -->
    <a-collapse ghost class="be-collapse">
      <a-collapse-panel key="skin" header="状态样式与动画（外观层）">
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
      </a-collapse-panel>
      <a-collapse-panel key="zonemap" header="状态 → 区域（3D 呈现路由）">
        <div v-for="(_, status) in draftStatusZoneMap" :key="status" class="be-zone-row">
          <span class="be-status-key">{{ status }}</span>
          <a-select v-model:value="draftStatusZoneMap[status]" class="be-zone-input" :options="zoneOptions" />
        </div>
      </a-collapse-panel>
    </a-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { officeApi, type BehaviorConfig, type DailyPlan, type OfficeConfig, type PlanSegment } from '@/api/office'

const props = defineProps<{
  behaviorConfig?: BehaviorConfig
  officeConfig?: OfficeConfig
  colleagues: Array<{ role_key?: string; name?: string; color?: string }>
}>()
const emit = defineEmits<{ saved: [] }>()

const saving = ref(false)
const draft = ref<BehaviorConfig>({ status_meta: {}, collaboration_rules: [] })
const draftStatusZoneMap = ref<Record<string, string>>({})
const auto = ref<NonNullable<BehaviorConfig['autonomous']>>(defaultAutonomous())
const brain = ref<NonNullable<BehaviorConfig['brain']>>(defaultBrain())
const mission = ref<NonNullable<BehaviorConfig['mission']>>(defaultMission())
const life = computed(() => auto.value.life)
const curRole = ref('')
const selKey = ref('')

const animationOptions = [
  { value: 'idle', label: '空闲' },
  { value: 'working', label: '工作' },
  { value: 'waiting', label: '等待' },
  { value: 'done', label: '完成' },
  { value: 'error', label: '异常' },
  { value: 'meeting', label: '协作' },
]

const TIMEZONES = [
  { value: 'Asia/Shanghai', label: '北京 UTC+8' },
  { value: 'UTC', label: 'UTC' },
  { value: 'Asia/Tokyo', label: '东京 UTC+9' },
  { value: 'Asia/Singapore', label: '新加坡 UTC+8' },
  { value: 'Europe/London', label: '伦敦 UTC+0' },
  { value: 'America/New_York', label: '纽约 UTC-5' },
]

const DAY_LABELS = ['一', '二', '三', '四', '五', '六', '日']

const STATUS_UI: Record<string, { cls: string; label: string; icon: string }> = {
  meeting: { cls: 'cat-meeting', label: '会议', icon: '🤝' },
  working: { cls: 'cat-work', label: '工作', icon: '💻' },
  idle: { cls: 'cat-rest', label: '休息', icon: '🍚' },
  waiting_input: { cls: 'cat-tea', label: '等候', icon: '☕' },
  thinking: { cls: 'cat-think', label: '思考', icon: '💭' },
  done: { cls: 'cat-done', label: '完成', icon: '✅' },
  public: { cls: 'cat-out', label: '公共', icon: '🚶' },
  error: { cls: 'cat-err', label: '异常', icon: '⚠️' },
}

const DAY_START = 540 // 09:00
const DAY_END = 1140 // 19:00

/* ── 默认值（与后端 _DEFAULT_DAILY_PLANS 镜像） ── */
function defaultDailyPlans(): DailyPlan[] {
  return [
    {
      id: 'weekday_common',
      label: '全员 · 工作日',
      roles: [],
      weekdays: [1, 2, 3, 4, 5],
      segments: [
        { start: '09:00', end: '09:30', status: 'meeting', intent: 'morning_sync', zone: 'meeting_room', activity: '参加晨会同步' },
        { start: '09:30', end: '12:00', status: 'working', intent: 'work', zone: 'desk_zone', activity: '{name} 进入上午工作块' },
        { start: '12:00', end: '13:30', status: 'idle', intent: 'lunch_break', zone: 'rest', activity: '午休时间' },
        { start: '13:30', end: '15:00', status: 'working', intent: 'work', zone: 'desk_zone', activity: '{name} 进入下午工作块' },
        { start: '15:00', end: '15:20', status: 'waiting_input', intent: 'tea_break', zone: 'tea', activity: '{name} 去茶水间歇口气' },
        { start: '15:20', end: '18:00', status: 'working', intent: 'work', zone: 'desk_zone', activity: '{name} 继续推进手头任务' },
        { start: '18:00', end: '18:30', status: 'thinking', intent: 'daily_review', zone: 'desk_zone', activity: '{name} 复盘今日进展与待办' },
      ],
    },
  ]
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
      llm_enabled: false,
      llm_budget_per_hour: 0,
      llm_min_interval_seconds: 180,
      llm_timeout_seconds: 12,
      llm_backoff_seconds: 300,
      interaction_enabled: true,
      interaction_cooldown_seconds: 300,
      allowed_zones: ['desk_zone', 'meeting_room', 'public_zone'],
      active_statuses: ['working', 'meeting', 'waiting_input', 'error'],
      interaction_action: {
        status: 'meeting',
        intent: 'discuss',
        zone: 'meeting_room',
        activity: '找同事简短沟通',
        message: '一起去会议室碰一下。',
      },
    },
    daily_plans: defaultDailyPlans(),
  }
}

function defaultBrain(): NonNullable<BehaviorConfig['brain']> {
  return { enabled: false, model_override: '', max_attempts: 1, generate_summary: true, generate_assignments: true, generate_conclusion: true }
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

function normalizeBrain(value?: BehaviorConfig['brain']): NonNullable<BehaviorConfig['brain']> {
  return { ...defaultBrain(), ...(value || {}) }
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

function normalizeAutonomous(value?: BehaviorConfig['autonomous']): NonNullable<BehaviorConfig['autonomous']> {
  const fallback = defaultAutonomous()
  if (!value) return fallback
  const fallbackLife = fallback.life
  const valueLife: any = value.life || {}
  const life = { ...fallbackLife }
  for (const key of Object.keys(fallbackLife)) {
    if (valueLife[key] !== undefined) (life as any)[key] = valueLife[key]
  }
  const plans: DailyPlan[] = Array.isArray(value.daily_plans) && value.daily_plans.length
    ? value.daily_plans.map((plan, i) => ({
        id: plan.id || `daily_plan_${i}`,
        label: plan.label || '',
        roles: Array.isArray(plan.roles) ? plan.roles.filter(Boolean) : [],
        weekdays: Array.isArray(plan.weekdays) && plan.weekdays.length ? plan.weekdays.filter((d) => d >= 1 && d <= 7) : [1, 2, 3, 4, 5, 6, 7],
        segments: (plan.segments || []).filter((s) => s && s.start && s.end),
      }))
    : defaultDailyPlans()
  // 显式字段组装：旧键（idle/schedule_rules/fallback_actions）不再回流
  return {
    enabled: value.enabled ?? fallback.enabled,
    tick_seconds: value.tick_seconds ?? fallback.tick_seconds,
    timezone: value.timezone || fallback.timezone,
    life,
    daily_plans: plans,
  }
}

/* ── 草稿同步 ── */
function cloneBehavior(value?: BehaviorConfig): BehaviorConfig {
  if (!value) return { status_meta: {}, collaboration_rules: [] }
  return JSON.parse(JSON.stringify(value))
}

function syncDraft() {
  const next = cloneBehavior(props.behaviorConfig)
  next.status_meta = next.status_meta || {}
  next.collaboration_rules = Array.isArray(next.collaboration_rules) ? next.collaboration_rules : []
  draft.value = next
  auto.value = normalizeAutonomous(next.autonomous)
  brain.value = normalizeBrain(next.brain)
  mission.value = normalizeMission(next.mission)
  draftStatusZoneMap.value = { ...(props.officeConfig?.status_zone_map || {}) }
  selKey.value = ''
}

watch(() => [props.behaviorConfig, props.officeConfig], syncDraft, { deep: true, immediate: true })

/* ── 基础视图 ── */
const officeZones = computed(() => props.officeConfig?.zones || [])
const zoneOptions = computed(() => officeZones.value.map((z) => ({ value: z.id, label: z.label || z.id })))
const colleagueList = computed(() => (props.colleagues || []).filter((c) => c.role_key))
const colleagueOptions = computed(() => colleagueList.value.map((c) => ({ value: c.role_key, label: c.name || c.role_key })))
const statusOptions = computed(() => [
  ...Object.keys(draft.value.status_meta || {}).map((key) => ({ value: key, label: draft.value.status_meta?.[key]?.label || key })),
  ...Object.keys(STATUS_UI)
    .filter((key) => !(key in (draft.value.status_meta || {})))
    .map((key) => ({ value: key, label: STATUS_UI[key].label })),
])

watch(
  colleagueList,
  (list) => {
    if ((!curRole.value || !list.some((c) => c.role_key === curRole.value)) && list.length) {
      curRole.value = list[0].role_key || ''
    }
  },
  { immediate: true },
)

interface ViewSeg {
  key: string
  planId: string
  planLabel: string
  shared: boolean
  planRef: DailyPlan
  seg: PlanSegment
}

function segmentsForRole(role: string): ViewSeg[] {
  const out: ViewSeg[] = []
  for (const plan of auto.value.daily_plans || []) {
    const roles = plan.roles || []
    if (roles.length && !roles.includes(role)) continue
    const planId = plan.id || 'plan'
    const planLabel = plan.label || (roles.length ? roles.join('、') : '全员计划')
    ;(plan.segments || []).forEach((seg, idx) => {
      if (!seg?.start || !seg?.end) return
      out.push({ key: `${role}:${planId}:${idx}`, planId, planLabel, shared: roles.length === 0, planRef: plan, seg })
    })
  }
  return out.sort((a, b) => (a.seg.start || '').localeCompare(b.seg.start || ''))
}

const lanes = computed(() =>
  colleagueList.value.map((c) => ({
    role: c.role_key || '',
    name: c.name || c.role_key || '',
    color: c.color || '#1677ff',
    segs: segmentsForRole(c.role_key || ''),
  })),
)

const allSegs = computed<ViewSeg[]>(() => lanes.value.flatMap((lane) => lane.segs))

const selectedSeg = computed(() => allSegs.value.find((v) => v.key === selKey.value) || null)
const planWeekdays = computed<number[]>(() => selectedSeg.value?.planRef.weekdays || [])

const nowTick = ref(Date.now())
let nowTimer = 0

const nowPct = computed(() => {
  const d = new Date(nowTick.value)
  const minutes = d.getHours() * 60 + d.getMinutes()
  return ((minutes - DAY_START) / (DAY_END - DAY_START)) * 100
})

function toMin(hhmm?: string): number {
  const [h, m] = String(hhmm || '0:0').split(':').map((n) => parseInt(n, 10) || 0)
  return h * 60 + m
}

function fromMin(total: number): string {
  const wrapped = ((total % 1440) + 1440) % 1440
  return `${String(Math.floor(wrapped / 60)).padStart(2, '0')}:${String(wrapped % 60).padStart(2, '0')}`
}

function pctOf(start?: string): string {
  return `${Math.max(0, ((toMin(start) - DAY_START) / (DAY_END - DAY_START)) * 100)}%`
}

function widthOf(seg: PlanSegment): string {
  const width = ((toMin(seg.end) - toMin(seg.start)) / (DAY_END - DAY_START)) * 100
  return `calc(${Math.max(0, width)}% - 3px)`
}

function statusClass(status?: string): string {
  return STATUS_UI[status || '']?.cls || 'cat-out'
}

function statusIcon(status?: string): string {
  return STATUS_UI[status || '']?.icon || '🚶'
}

function zoneLabel(zoneId?: string): string {
  return officeZones.value.find((z) => z.id === zoneId)?.label || zoneId || ''
}

function segTitle(vs: ViewSeg): string {
  return (vs.seg.activity || '').replace(/\{name\}/g, '').trim() || STATUS_UI[vs.seg.status || '']?.label || vs.seg.intent || '日程段'
}

function laneTailGap(lane: { segs: ViewSeg[] }): number {
  const lastEnd = lane.segs.length ? Math.min(DAY_END, toMin(lane.segs[lane.segs.length - 1].seg.end)) : DAY_START
  return DAY_END - lastEnd
}

function laneTailLeft(lane: { segs: ViewSeg[] }): string {
  const lastEnd = lane.segs.length ? Math.min(DAY_END, toMin(lane.segs[lane.segs.length - 1].seg.end)) : DAY_START
  return `${((lastEnd - DAY_START) / (DAY_END - DAY_START)) * 100}%`
}

function onSegDown(event: PointerEvent, vs: ViewSeg, lane: { segs: ViewSeg[] }) {
  const target = event.target as HTMLElement
  const mode = target.classList.contains('h') ? (target.classList.contains('hl') ? 'l' : 'r') : 'move'
  event.preventDefault()
  const el = event.currentTarget as HTMLElement
  const track = el.parentElement
  if (!track) return
  const rect = track.getBoundingClientRect()
  const list = lane.segs

  const idx = list.findIndex((item) => item.key === vs.key)
  const prev = list[idx - 1]
  const next = list[idx + 1]
  const startX = event.clientX
  const startMin = toMin(vs.seg.start)
  const endMin = toMin(vs.seg.end)
  const duration = endMin - startMin
  let moved = false
  el.setPointerCapture(event.pointerId)

  const move = (ev: PointerEvent) => {
    if (Math.abs(ev.clientX - startX) > 3) moved = true
    if (!moved) return
    const delta = ((ev.clientX - startX) / rect.width) * (DAY_END - DAY_START)
    const snap = (v: number) => Math.round(v / 5) * 5
    if (mode === 'move') {
      const lo = prev ? toMin(prev.seg.end) : DAY_START
      const hi = next ? toMin(next.seg.start) : DAY_END
      const nextStart = Math.max(lo, Math.min(snap(startMin + delta), hi - duration, DAY_END - duration))
      vs.seg.start = fromMin(nextStart)
      vs.seg.end = fromMin(nextStart + duration)
    } else if (mode === 'l') {
      const lo = prev ? toMin(prev.seg.end) : DAY_START
      vs.seg.start = fromMin(Math.max(lo, Math.min(snap(toMinuteAt(ev.clientX, rect)), endMin - 15)))
    } else {
      const hi = next ? toMin(next.seg.start) : DAY_END
      vs.seg.end = fromMin(Math.min(hi, Math.max(snap(toMinuteAt(ev.clientX, rect)), startMin + 15)))
    }
  }
  const up = () => {
    el.removeEventListener('pointermove', move)
    el.removeEventListener('pointerup', up)
    if (!moved && mode === 'move') selKey.value = vs.key
  }
  el.addEventListener('pointermove', move)
  el.addEventListener('pointerup', up)
}

function toMinuteAt(clientX: number, rect: DOMRect): number {
  return DAY_START + ((clientX - rect.left) / rect.width) * (DAY_END - DAY_START)
}

/* ── 段编辑 ── */
function ensurePersonPlan(role: string, name: string): DailyPlan {
  const existing = (auto.value.daily_plans || []).find(
    (plan) => (plan.roles || []).length === 1 && plan.roles?.[0] === role,
  )
  if (existing) return existing
  const created: DailyPlan = {
    id: `plan_${role}_${Date.now()}`,
    label: `${name} · 个人`,
    roles: [role],
    weekdays: [1, 2, 3, 4, 5],
    segments: [],
  }
  auto.value.daily_plans.push(created)
  return created
}

function addSegment(lane: { role: string; name: string; segs: ViewSeg[] }) {
  curRole.value = lane.role
  const lastEnd = lane.segs.length ? Math.min(DAY_END, toMin(lane.segs[lane.segs.length - 1].seg.end)) : DAY_START
  if (DAY_END - lastEnd < 30) {
    message.warning('这一天已排满，先腾出空档再新增')
    return
  }
  const plan = ensurePersonPlan(lane.role, lane.name)
  plan.segments.push({
    start: fromMin(lastEnd),
    end: fromMin(Math.min(lastEnd + 60, DAY_END)),
    status: 'working',
    intent: 'work',
    zone: officeZones.value[0]?.id || 'desk_zone',
    activity: '',
  })
  selKey.value = `${lane.role}:${plan.id}:${plan.segments.length - 1}`
}

function removeSegment() {
  const vs = selectedSeg.value
  if (!vs) return
  const plan = auto.value.daily_plans.find((p) => p.id === vs.planId)
  if (!plan) return
  const idx = plan.segments.indexOf(vs.seg)
  if (idx >= 0) plan.segments.splice(idx, 1)
  if (plan !== vs.planRef) return
  if (!plan.segments.length && (plan.roles || []).length) {
    auto.value.daily_plans = auto.value.daily_plans.filter((p) => p.id !== plan.id)
  }
  selKey.value = ''
}

function toggleWeekday(day: number) {
  const plan = selectedSeg.value?.planRef
  if (!plan) return
  const days = plan.weekdays || []
  if (days.includes(day)) {
    if (days.length <= 1) {
      message.warning('至少保留一个生效日')
      return
    }
    plan.weekdays = days.filter((d) => d !== day)
  } else {
    plan.weekdays = [...days, day].sort((a, b) => a - b)
  }
}

function addCollabRule() {
  if (!draft.value.collaboration_rules) draft.value.collaboration_rules = []
  draft.value.collaboration_rules.push({
    when: 'same_thread_id',
    min_members: 2,
    zone: officeZones.value.find((z) => z.type === 'meeting')?.id || 'meeting_room',
    cooldown_seconds: 300,
  })
}

/* ── 代理绑定（antd 需要 number / string 非空值） ── */
const budgetProxy = computed({
  get: () => life.value.llm_budget_per_hour ?? 0,
  set: (v: number) => { life.value.llm_budget_per_hour = v },
})
const brainModelProxy = computed({
  get: () => brain.value.model_override || '',
  set: (v: string) => { brain.value.model_override = v || null },
})
const missionOwnerProxy = computed({
  get: () => mission.value.owner_role_key || undefined,
  set: (v: string) => { mission.value.owner_role_key = v || undefined },
})

const collabRules = computed(() => draft.value.collaboration_rules || [])
const tzProxy = computed({
  get: () => auto.value.timezone || 'Asia/Shanghai',
  set: (v: string) => { auto.value.timezone = v },
})


/* ── 保存 ── */
async function save() {
  saving.value = true
  try {
    for (const plan of auto.value.daily_plans || []) {
      plan.segments = (plan.segments || [])
        .filter((s) => s && s.start && s.end && toMin(s.end) > toMin(s.start))
        .sort((a, b) => (a.start || '').localeCompare(b.start || ''))
    }
    await officeApi.updateBehavior({
      ...(draft.value || {}),
      status_meta: draft.value.status_meta,
      collaboration_rules: draft.value.collaboration_rules,
      autonomous: {
        enabled: auto.value.enabled,
        tick_seconds: auto.value.tick_seconds,
        timezone: auto.value.timezone,
        life: { ...auto.value.life },
        daily_plans: auto.value.daily_plans,
      },
      brain: brain.value,
      mission: mission.value,
    })
    await officeApi.updateLayout({
      office: {
        ...(props.officeConfig || {}),
        status_zone_map: draftStatusZoneMap.value,
      },
    })
    message.success('行为配置已保存')
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '行为配置保存失败')
  } finally {
    saving.value = false
  }
}

/* ── 生命周期 ── */
onMounted(() => {
  nowTimer = window.setInterval(() => { nowTick.value = Date.now() }, 30000)
  if (!curRole.value && colleagueList.value.length) curRole.value = colleagueList.value[0].role_key || ''
})

onUnmounted(() => {
  clearInterval(nowTimer)
})

defineExpose({ save })
</script>

<style scoped>
/* ── 组件局部调色板：浅色默认，暗色在 [data-theme='dark'] 整体覆盖 ── */
.behavior-editor {
  /* 玻璃面 */
  --be-glass: var(--cpq-glass-2-bg);
  --be-glass-weak: var(--cpq-glass-1-bg);
  --be-glass-strong: var(--cpq-glass-3-bg);
  --be-border: var(--cpq-glass-border);
  --be-border-strong: var(--cpq-glass-border-strong);
  --be-highlight: rgba(255, 255, 255, 0.85);
  --be-blur: var(--cpq-glass-blur-2, 12px);
  --be-shadow: var(--cpq-glass-card-shadow);
  --be-ink: var(--cpq-text-primary);
  --be-ink2: var(--cpq-text-secondary);
  --be-ink3: var(--cpq-text-muted);
  /* 日程段（浅底 = 马卡龙 tint + 深色前景） */
  --seg-meeting-bg: rgba(146, 84, 222, 0.15); --seg-meeting-fg: #6b2bb5;
  --seg-work-bg: rgba(22, 119, 255, 0.13);    --seg-work-fg: #1250b8;
  --seg-rest-bg: rgba(82, 201, 160, 0.18);    --seg-rest-fg: #1d8f68;
  --seg-tea-bg: rgba(250, 140, 22, 0.16);     --seg-tea-fg: #c26e0a;
  --seg-think-bg: rgba(19, 194, 194, 0.15);   --seg-think-fg: #0e8f8f;
  --seg-done-bg: rgba(82, 201, 160, 0.26);    --seg-done-fg: #1d7a58;
  --seg-out-bg: rgba(120, 144, 176, 0.18);    --seg-out-fg: #54677f;
  --seg-err-bg: rgba(255, 107, 107, 0.15);    --seg-err-fg: #c0392b;
  /* 日志徽标 */
  --bd-sched-fg: #1250b8; --bd-sched-bg: rgba(22, 119, 255, 0.10);
  --bd-task-fg: #c0392b;  --bd-task-bg: rgba(255, 107, 107, 0.14);
  --bd-llm-fg: #237804;   --bd-llm-bg: rgba(82, 201, 160, 0.16);
  --bd-idle-fg: #0e8f8f;  --bd-idle-bg: rgba(19, 194, 194, 0.12);
  /* 语义点缀 */
  --be-warn-fg: #c26e0a; --be-warn-bg: rgba(250, 140, 22, 0.1); --be-warn-border: rgba(250, 140, 22, 0.25);
  --be-danger: #e5484d;
  --be-blue: #1677ff;

  padding: 16px;
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

[data-theme='dark'] .behavior-editor {
  --be-highlight: rgba(255, 255, 255, 0.10);
  --seg-meeting-bg: rgba(146, 84, 222, 0.22); --seg-meeting-fg: #c9a8ff;
  --seg-work-bg: rgba(77, 137, 255, 0.20);    --seg-work-fg: #8ab4ff;
  --seg-rest-bg: rgba(82, 201, 160, 0.16);    --seg-rest-fg: #7fe0c0;
  --seg-tea-bg: rgba(250, 140, 22, 0.16);     --seg-tea-fg: #ffc069;
  --seg-think-bg: rgba(19, 194, 194, 0.14);   --seg-think-fg: #6fe0e0;
  --seg-done-bg: rgba(82, 201, 160, 0.22);    --seg-done-fg: #52c9a0;
  --seg-out-bg: rgba(120, 144, 176, 0.14);    --seg-out-fg: #a9b7c9;
  --seg-err-bg: rgba(255, 107, 107, 0.14);    --seg-err-fg: #ff8f8f;
  --bd-sched-fg: #8ab4ff; --bd-sched-bg: rgba(77, 137, 255, 0.16);
  --bd-task-fg: #ff8f8f;  --bd-task-bg: rgba(255, 107, 107, 0.14);
  --bd-llm-fg: #7fe0c0;   --bd-llm-bg: rgba(82, 201, 160, 0.14);
  --bd-idle-fg: #6fe0e0;  --bd-idle-bg: rgba(19, 194, 194, 0.12);
  --be-warn-fg: #ffc069; --be-warn-bg: rgba(250, 140, 22, 0.12); --be-warn-border: rgba(250, 140, 22, 0.28);
  --be-danger: #ff6b6b;
}

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
.be-toolbar h3 { margin: 0; font-size: 18px; color: var(--be-ink); }
.be-toolbar p { margin: 4px 0 0; color: var(--be-ink3); font-size: 12px; }

/* ── 全局条 ── */
.be-global {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  background: var(--be-glass-weak);
  backdrop-filter: blur(var(--be-blur));
  -webkit-backdrop-filter: blur(var(--be-blur));
  border: 1px solid var(--be-border);
  border-radius: 16px;
  box-shadow: var(--be-shadow);
  padding: 9px 16px;
  font-size: 12.5px;
  color: var(--be-ink2);
}
.gb-item { display: flex; align-items: center; gap: 7px; white-space: nowrap; }
.gb-item b { color: var(--be-ink); }
.gb-num { width: 74px; }
.gb-tz { width: 150px; }
.gb-slider { width: 110px; margin: 0 4px; }
.gb-sep { width: 1px; height: 18px; background: var(--be-border); }
.gb-hint { font-size: 11px; color: var(--be-warn-fg); background: var(--be-warn-bg); border: 1px solid var(--be-warn-border); padding: 1px 8px; border-radius: 999px; }

/* ── 区块（单层玻璃卡：blur 只在这一层） ── */
.be-section {
  border: 1px solid var(--be-border);
  border-radius: 20px;
  padding: 14px 16px;
  background: var(--be-glass);
  backdrop-filter: blur(var(--be-blur));
  -webkit-backdrop-filter: blur(var(--be-blur));
  box-shadow: var(--be-shadow), inset 0 1px 0 var(--be-highlight);
}
.be-card-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.be-title { font-size: 14.5px; font-weight: 700; display: flex; align-items: center; gap: 8px; color: var(--be-ink); }
.be-sub { font-size: 11px; font-weight: 500; color: var(--be-ink3); background: var(--cpq-overlay-w10, rgba(120, 144, 176, 0.12)); padding: 1px 8px; border-radius: 999px; }
.be-tag-note { font-size: 11px; font-weight: 500; color: var(--be-ink3); background: var(--cpq-overlay-w10, rgba(120, 144, 176, 0.12)); padding: 1px 8px; border-radius: 999px; }
.be-section-title { margin-bottom: 10px; color: var(--be-ink2); font-size: 13px; font-weight: 700; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

/* ── 泳道时间轴 ── */
.tl-wrap { display: flex; flex-direction: column; }
.swim { display: flex; flex-direction: column; }
.swim-row { display: flex; align-items: stretch; gap: 10px; padding: 2px 0; }
.swim-row.active .swim-track { background: var(--cpq-overlay-w5, rgba(22, 119, 255, 0.04)); border-radius: 10px; }
.swim-label {
  width: 116px; flex: none; display: flex; align-items: center; gap: 7px; padding: 4px 8px;
  border: 1px solid transparent; border-radius: 9px; background: none; cursor: pointer;
  font-size: 12px; color: var(--be-ink2); text-align: left; font-family: inherit; overflow: hidden;
}
.swim-label i { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.swim-label .swim-name { white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
.swim-row.active .swim-label { background: var(--be-glass-strong); border-color: var(--be-border-strong); color: var(--be-ink); font-weight: 600; }
.swim-row--head .swim-label--head { border: none; background: none; cursor: default; }
.swim-track { position: relative; flex: 1; min-width: 0; height: 46px; }
.swim-axis { position: relative; flex: 1; height: 16px; line-height: 16px; font-size: 10.5px; color: var(--be-ink3); font-family: ui-monospace, Consolas, monospace; }
.swim-axis span { position: absolute; transform: translateX(-50%); }
.swim-track .seg { top: 3px; bottom: 3px; padding: 3px 10px; gap: 0; }
.swim-track .seg .t { font-size: 11px; line-height: 1.35; }
.swim-track .seg .tm { font-size: 9px; line-height: 1.3; text-overflow: ellipsis; }

.seg {
  position: absolute; top: 6px; bottom: 6px; border-radius: 9px; padding: 5px 8px; overflow: hidden;
  cursor: pointer; transition: box-shadow 0.15s; display: flex; flex-direction: column; justify-content: center; gap: 1px;
  box-shadow: inset 0 1px 0 var(--be-highlight); touch-action: none; user-select: none;
}
.seg:hover { box-shadow: 0 4px 12px var(--cpq-shadow-color-soft, rgba(22, 119, 255, 0.14)); }
.seg.sel { outline: 2px solid var(--be-blue); outline-offset: 1px; }
.seg .t { font-size: 11.5px; font-weight: 600; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
.seg .tm { font-size: 9.5px; opacity: 0.78; font-family: ui-monospace, Consolas, monospace; white-space: nowrap; }
.seg.mini .t, .seg.mini .tm { display: none; }
.seg.mini::after { content: '☕'; position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; }
.seg .h { position: absolute; top: 0; bottom: 0; width: 8px; cursor: ew-resize; z-index: 2; }
.seg .h.hl { left: 0; }
.seg .h.hr { right: 0; }
.seg .h::after { content: ''; position: absolute; top: 50%; transform: translateY(-50%); width: 3px; height: 16px; border-radius: 2px; background: var(--be-highlight); opacity: 0; transition: 0.15s; }
.seg:hover .h::after { opacity: 1; }
.seg .h.hl::after { left: 2px; }
.seg .h.hr::after { right: 2px; }

.cat-meeting { background: var(--seg-meeting-bg); color: var(--seg-meeting-fg); }
.cat-work { background: var(--seg-work-bg); color: var(--seg-work-fg); }
.cat-rest { background: var(--seg-rest-bg); color: var(--seg-rest-fg); }
.cat-tea { background: var(--seg-tea-bg); color: var(--seg-tea-fg); }
.cat-think { background: var(--seg-think-bg); color: var(--seg-think-fg); }
.cat-done { background: var(--seg-done-bg); color: var(--seg-done-fg); }
.cat-out { background: var(--seg-out-bg); color: var(--seg-out-fg); }
.cat-err { background: var(--seg-err-bg); color: var(--seg-err-fg); }

.nowline { position: absolute; top: -8px; bottom: -4px; width: 2px; background: var(--be-danger); border-radius: 2px; pointer-events: none; z-index: 3; }
.nowline span { position: absolute; top: -14px; left: -14px; font-size: 9.5px; color: var(--be-danger); white-space: nowrap; }

.add-tail {
  position: absolute; top: 8px; bottom: 8px; border: 1.5px dashed var(--be-border);
  border-radius: 9px; display: flex; align-items: center; justify-content: center; color: var(--be-ink3);
  font-size: 12px; cursor: pointer; transition: 0.15s; background: var(--cpq-overlay-w5, rgba(255, 255, 255, 0.25));
}
.add-tail:hover { color: var(--be-blue); border-color: var(--be-border-strong); background: rgba(22, 119, 255, 0.05); }

.legend { display: flex; gap: 12px; font-size: 11px; color: var(--be-ink3); margin-top: 8px; flex-wrap: wrap; }
.legend em { font-style: normal; display: flex; align-items: center; gap: 5px; }
.legend em::before { content: ''; width: 9px; height: 9px; border-radius: 3px; background: currentColor; opacity: 0.4; }
.prio-note { margin-top: 7px; font-size: 11px; color: var(--be-ink2); }
.prio-note b { color: var(--be-danger); font-weight: 600; }

/* ── 段编辑器 ── */
.seg-editor { margin-top: 14px; border-top: 1px dashed var(--be-border); padding-top: 12px; }
.se-empty { color: var(--be-ink3); font-size: 12px; }
.se-title { font-size: 12px; color: var(--be-ink2); margin-bottom: 10px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.se-title b { color: var(--be-ink); }
.se-tag { margin-right: 0; }
.se-plan { font-size: 11px; color: var(--be-ink3); }
.se-plan-hint { font-size: 10.5px; color: var(--be-ink3); margin-left: 8px; }
.se-grid { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
.fld { display: flex; flex-direction: column; gap: 4px; }
.fld label { font-size: 10.5px; color: var(--be-ink3); }
.se-wide { width: 300px; }
.se-mid { width: 130px; }
.se-time { width: 76px; font-family: ui-monospace, Consolas, monospace; }
.del-seg { font-size: 11.5px; color: var(--be-danger); background: none; border: 1px solid rgba(255, 107, 107, 0.35); border-radius: 8px; padding: 3px 12px; cursor: pointer; }
.del-seg:hover { background: rgba(255, 107, 107, 0.08); }
.se-weekdays { margin-top: 10px; display: flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--be-ink2); flex-wrap: wrap; }
.wd { font-size: 11px; padding: 2px 8px; border-radius: 7px; color: var(--be-ink3); cursor: pointer; border: 1px solid transparent; background: none; }
.wd.on { color: var(--be-blue); background: rgba(22, 119, 255, 0.1); font-weight: 600; }

/* ── 智能层 ── */
.smart-row { display: flex; align-items: center; gap: 8px; padding: 8px 2px; border-bottom: 1px dashed var(--be-border); font-size: 12.5px; flex-wrap: wrap; }
.smart-row .name { font-weight: 600; min-width: 64px; color: var(--be-ink); }
.smart-row .desc { color: var(--be-ink3); font-size: 11.5px; flex: 1; min-width: 140px; }
.smart-sub { display: flex; align-items: center; gap: 8px; padding: 5px 2px 5px 30px; font-size: 12px; color: var(--be-ink2); flex-wrap: wrap; }
.mission-row { border-top: 1px dashed var(--be-border); margin-top: 6px; }
.se-add { margin-top: 4px; }

/* ── 折叠外观层 ── */
.be-collapse { background: var(--be-glass-weak); border: 1px solid var(--be-border); border-radius: 16px; padding: 0 12px; }
.be-status-row { display: grid; grid-template-columns: 110px minmax(110px, 1fr) 46px 100px 76px 120px; gap: 8px; align-items: center; margin-bottom: 8px; }
.be-zone-row { display: grid; grid-template-columns: 150px 1fr; gap: 8px; align-items: center; margin-bottom: 8px; }
.be-status-key { color: var(--be-ink2); font-family: ui-monospace, monospace; font-size: 12px; }
.be-check { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--be-ink3); }
.be-opacity-input, .be-animation-input, .be-zone-input, .be-label-input { width: 100%; }
</style>
