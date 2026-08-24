<template>
  <section class="tc-root">
    <header class="tc-header">
      <div class="tc-heading">
        <div class="tc-kicker">AI OFFICE / TASK CENTER</div>
        <h2>{{ viewTitle }}</h2>
        <p>{{ viewSub }}</p>
      </div>
      <div class="tc-actions">
        <a-input v-model:value="search" class="tc-search" placeholder="搜索任务、负责人、交付物" allow-clear />
        <a-button size="small" :loading="loading" @click="$emit('refresh')">刷新</a-button>
        <a-button type="primary" size="small" @click="openCreate">新建任务</a-button>
        <a-button type="text" size="small" @click="$emit('close')">关闭</a-button>
      </div>
    </header>

    <nav class="tc-nav">
      <button
        v-for="tab in viewTabs"
        :key="tab.key"
        class="tc-nav-btn"
        :class="{ active: view === tab.key }"
        type="button"
        @click="view = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <section v-if="view === 'timeline'" class="tc-timeline">
      <div class="tc-section-toolbar">
        <div>
          <div class="tc-section-title">周时间线</div>
          <div class="tc-section-sub">按当前周查看任务安排，同色任务条代表同一状态。</div>
        </div>
        <div class="tc-section-nav">
          <a-button size="small" @click="moveWeek(-1)">‹</a-button>
          <a-button size="small" @click="weekStart = startOfWeek(new Date())">本周</a-button>
          <a-button size="small" @click="moveWeek(1)">›</a-button>
          <span class="tc-week-label">{{ weekLabel }}</span>
        </div>
      </div>

      <div class="tc-gantt">
        <div class="tc-gantt-scroll">
          <div class="tc-gantt-header">
            <div class="tc-gantt-corner">任务 / 负责人</div>
            <div
              v-for="(day, index) in weekDays"
              :key="index"
              class="tc-gantt-day"
              :class="{ today: isSameDay(day, today), weekend: index >= 5 }"
            >
              <b>{{ weekDayLabel[index] }}</b>{{ formatDateLabel(day) }}
            </div>
          </div>
          <div class="tc-gantt-body">
            <div v-for="row in visibleTimelineRows" :key="row.id" class="tc-gantt-row">
              <div class="tc-gantt-label"><b>{{ row.label }}</b><small>{{ row.owner }}</small></div>
              <div class="tc-gantt-track">
                <button
                  class="tc-gantt-bar"
                  :style="ganttBarStyle(row)"
                  type="button"
                  @click="openMission(row.missionId)"
                >
                  {{ row.label }}
                </button>
              </div>
            </div>
            <div v-if="!visibleTimelineRows.length" class="tc-empty">本周暂无任务安排</div>
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="view === 'calendar'" class="tc-calendar">
      <div class="tc-section-toolbar">
        <div>
          <div class="tc-section-title">日历</div>
          <div class="tc-section-sub">整月查看任务排期，同一任务跨天使用同一颜色。</div>
        </div>
        <div class="tc-section-nav">
          <a-button size="small" @click="moveMonth(-1)">‹</a-button>
          <a-button size="small" @click="currentMonth = new Date()">今天</a-button>
          <a-button size="small" @click="moveMonth(1)">›</a-button>
          <span class="tc-week-label">{{ calendarTitle }}</span>
        </div>
      </div>

      <div class="tc-cal-grid">
        <div v-for="weekday in weekDayLabel" :key="weekday" class="tc-cal-weekday">{{ weekday }}</div>
        <div
          v-for="cell in calendarCells"
          :key="cell.key"
          class="tc-cal-cell"
          :class="{ muted: cell.muted, today: isSameDay(cell.date, today) }"
        >
          <div class="tc-cal-day-num"><b>{{ cell.day }}</b></div>
          <button
            v-for="mission in cell.missions"
            :key="mission.mission_id"
            class="tc-cal-event"
            :style="{ background: missionColor(mission) }"
            type="button"
            :title="mission.prompt"
            @click="openMission(mission.mission_id)"
          >
            {{ mission.prompt }}
          </button>
        </div>
      </div>
    </section>

    <section v-else class="tc-deliverables">
      <div class="tc-section-toolbar">
        <div>
          <div class="tc-section-title">交付物中心</div>
          <div class="tc-section-sub">以列表统一查看 AI 任务产出的方案、草稿和写库结果。</div>
        </div>
      </div>
      <div class="tc-dv-summary">共 <b>{{ filteredDeliverableRows.length }}</b> 项 · 涉及任务 <b>{{ deliverableTaskCount }}</b> 个</div>
      <div class="tc-dv-list">
        <div class="tc-dv-row tc-dv-head-row">
          <div>交付物</div>
          <div>所属任务</div>
          <div>来源</div>
          <div>负责人</div>
          <div>状态</div>
          <div>更新时间</div>
        </div>
        <button
          v-for="row in filteredDeliverableRows"
          :key="row.id"
          class="tc-dv-row"
          type="button"
          @click="openMission(row.mission.mission_id)"
        >
          <div class="tc-dv-title-cell">
            <b>{{ deliverableTitle(row.deliverable) }}</b>
            <span>{{ deliverableContent(row.deliverable) }}</span>
          </div>
          <div class="tc-dv-task-cell"><b>{{ row.mission.prompt }}</b><small>{{ row.mission.mission_id }}</small></div>
          <div>{{ sourceLabel(row.mission.source) }}</div>
          <div>{{ colleagueName(row.mission.owner_role_key) }}</div>
          <div><span class="tc-status" :style="{ '--status-color': statusColor(row.mission.status) }">{{ missionStatusLabel(row.mission.status) }}</span></div>
          <div>{{ formatTime(row.mission.updated_at || row.mission.created_at) }}</div>
        </button>
        <div v-if="!filteredDeliverableRows.length" class="tc-empty">暂无交付物</div>
      </div>
    </section>
    <a-drawer
      v-model:open="detailOpen"
      title="任务详情"
      placement="right"
      :width="520"
      :get-container="getBodyContainer"
    >
      <template v-if="selectedMission">
        <div class="td-section">
          <div class="td-label">任务目标</div>
          <div class="td-value">{{ selectedMission.prompt }}</div>
          <div class="td-meta">
            <span>发起人：{{ selectedMission.created_by || '用户' }}</span>
            <span>负责人：{{ colleagueName(selectedMission.owner_role_key) }}</span>
            <span v-if="selectedMission.completed_at">完成：{{ formatTime(selectedMission.completed_at) }}</span>
          </div>
        </div>

        <div v-if="selectedMission.opportunity_id || selectedMission.flow_node || selectedMission.skill_key" class="td-section">
          <div class="td-label">业务关联</div>
          <div class="td-meta">
            <span v-if="isRealOpportunity(selectedMission.opportunity_id)">
              商机：
              <a-button type="link" size="small" @click="openOpportunity(selectedMission.opportunity_id!)">{{ selectedMission.opportunity_id }}</a-button>
            </span>
            <span v-if="selectedMission.flow_node">流程节点：{{ selectedMission.flow_node }}</span>
            <span v-if="selectedMission.skill_key">Skill：{{ selectedMission.skill_key }}</span>
          </div>
        </div>

        <div v-if="selectedMission.artifacts?.length" class="td-section">
          <div class="td-label">产出物草稿</div>
          <div v-for="(artifact, index) in selectedMission.artifacts" :key="index" class="td-report">
            <div class="td-report-title">{{ artifact.title || artifact.type || '产出物' }}</div>
            <div v-if="artifactSummary(artifact)" class="td-report-content">{{ artifactSummary(artifact) }}</div>
            <a-button type="link" size="small" @click="openArtifact(artifact)">{{ artifactViewFromArtifact(artifact) ? '打开方案' : '查看内容' }}</a-button>
          </div>
        </div>

        <div class="td-actions">
          <a-button
            v-if="selectedMission.artifacts?.length"
            size="small"
            type="primary"
            @click="openArtifact(selectedMission.artifacts[0])"
          >
            查看产出物
          </a-button>
          <a-button v-if="['queued','running'].includes(selectedMission.status)" size="small" :loading="actionLoading" @click="cancelSelected">取消</a-button>
          <a-button v-if="selectedMission.status === 'failed'" size="small" type="primary" :loading="actionLoading" @click="retrySelected">重试</a-button>
          <a-button size="small" danger :loading="actionLoading" @click="deleteSelected">删除</a-button>
        </div>

        <div v-if="selectedMission.deliverables?.length" class="td-section">
          <div class="td-label">任务成果</div>
          <div v-for="(deliverable, index) in selectedMission.deliverables" :key="index" class="td-report">
            <div class="td-report-title">{{ deliverableTitle(deliverable) }}</div>
            <div class="td-report-content">{{ deliverableContent(deliverable) }}</div>
          </div>
        </div>

        <div class="td-section">
          <div class="td-label">执行时间线</div>
          <div v-if="!selectedMission.steps?.length" class="td-empty">暂无步骤</div>
          <div v-for="step in selectedMission.steps" :key="step.assignment_id || step.step_id" class="td-step">
            <div class="td-step-head">
              <span>{{ colleagueName(step.completed_by || step.role_key) }}</span>
              <span>{{ assignmentStatusLabel(step.assignment_status) }}</span>
              <span v-if="step.completed_at">{{ formatTime(step.completed_at) }}</span>
            </div>
            <div class="td-step-task">{{ step.task }}</div>
            <div v-if="step.result_summary" class="td-step-result">{{ step.result_summary }}</div>
          </div>
        </div>
      </template>
    </a-drawer>

    <a-modal
      v-model:open="artifactPreviewOpen"
      :title="artifactTitle || '产出物预览'"
      :footer="null"
      width="min(1180px, calc(100vw - 24px))"
      :z-index="1800"
      :body-style="{ padding: '14px', maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', overflowX: 'hidden' }"
    >
      <BusinessArtifactView
        v-if="artifactView"
        :entity-type="artifactView.entityType"
        :entity="artifactView.entity"
        inline
      />
      <div v-else-if="artifactContent" class="td-report-content">{{ artifactContent }}</div>
      <div v-if="artifactPlans.length" class="td-artifact-plans">
        <PlanCard
          v-for="plan in artifactPlans"
          :key="plan.config_id"
          :plan="plan"
          @view-bom="openArtifactBom(plan)"
        />
      </div>
      <a-empty v-if="!artifactView && !artifactContent && !artifactPlans.length" description="该产出物暂无可预览内容" />
    </a-modal>

    <a-modal
      v-model:open="artifactBomOpen"
      :title="artifactBomPlan?.name || '整机 BOM 详情'"
      :footer="null"
      width="720px"
      :z-index="1850"
      :body-style="{ padding: '14px', maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', overflowX: 'hidden' }"
    >
      <div v-if="artifactBomPlan" class="td-report-content">
        {{ [artifactBomPlan.series, artifactBomPlan.form, artifactBomPlan.bays != null ? `${artifactBomPlan.bays}盘位` : ''].filter(Boolean).join(' · ') }}
      </div>
      <a-spin :spinning="artifactBomLoading" tip="转 BOM 模板格式…">
        <BomTable v-if="artifactBomCfg" :cfg="artifactBomCfg" />
      </a-spin>
    </a-modal>

    

    <a-modal
      v-model:open="createOpen"
      title="新建任务"
      :footer="null"
      width="560"
      :get-container="getBodyContainer"
    >
      <div class="tc-modal-form">
        <label class="tc-field">
          <span>任务目标</span>
          <a-textarea v-model:value="createForm.prompt" :auto-size="{ minRows: 3, maxRows: 7 }" placeholder="描述需要 AI 员工完成的工作" />
        </label>
        <label class="tc-field">
          <span>负责人</span>
          <a-select v-model:value="createForm.owner_role_key" allow-clear placeholder="留空交给 Leader 分配" style="width: 100%">
            <a-select-option v-for="colleague in colleagues" :key="colleague.role_key" :value="colleague.role_key">
              {{ colleague.name || colleague.role_key }}
            </a-select-option>
          </a-select>
        </label>
        <label class="tc-field">
          <span>优先级</span>
          <a-radio-group v-model:value="createForm.priority" button-style="solid" size="small">
            <a-radio-button value="low">低</a-radio-button>
            <a-radio-button value="medium">中</a-radio-button>
            <a-radio-button value="high">高</a-radio-button>
          </a-radio-group>
        </label>
      </div>
      <div class="tc-modal-actions">
        <a-button @click="createOpen = false">取消</a-button>
        <a-button type="primary" :loading="actionLoading" @click="createMission">创建任务</a-button>
      </div>
    </a-modal>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import BomTable from '@/components/BomTable.vue'
import PlanCard from '@/components/reasoning/PlanCard.vue'
import BusinessArtifactView from '@/components/assistant/BusinessArtifactView.vue'
import { officeApi, type BehaviorConfig, type OfficeDeliverable, type OfficeMission, type OfficeMissionStep } from '@/api/office'
import type { Plan } from '@/api/reasoning'
import { buildPlanCfg, type PlanLiveCfg } from '@/composables/usePlanBom'

const router = useRouter()

type ViewKey = 'timeline' | 'calendar' | 'deliverables'
interface TimelineRow {
  id: string
  label: string
  owner: string
  start: Date
  end: Date
  color: string
  missionId: string
}
interface DeliverableRow {
  id: string
  mission: OfficeMission
  deliverable: OfficeDeliverable
  sourceStep?: OfficeMissionStep
}
interface CalendarCell {
  key: string
  day: number
  date: Date
  muted: boolean
  missions: OfficeMission[]
}
interface ArtifactViewData {
  entityType: string
  entity: any
}

const props = defineProps<{
  missions: OfficeMission[]
  colleagues: any[]
  behaviorConfig: BehaviorConfig
  loading?: boolean
}>()

const emit = defineEmits<{
  close: []
  refresh: []
  changed: []
}>()

const view = ref<ViewKey>('timeline')
const search = ref('')
const selectedMissionId = ref<string | null>(null)
const detailOpen = ref(false)
const actionLoading = ref(false)
const createOpen = ref(false)
const createForm = ref({
  prompt: '',
  owner_role_key: undefined as string | undefined,
  priority: 'medium',
})
const artifactPreviewOpen = ref(false)
const artifactTitle = ref('')
const artifactContent = ref('')
const artifactPlans = ref<Plan[]>([])
const artifactView = ref<ArtifactViewData | null>(null)
const artifactBomOpen = ref(false)
const artifactBomPlan = ref<Plan | null>(null)
const artifactBomCfg = ref<PlanLiveCfg | null>(null)
const artifactBomLoading = ref(false)
const weekStart = ref(startOfWeek(new Date()))
const currentMonth = ref(new Date())

const viewTabs: Array<{ key: ViewKey; label: string }> = [
  { key: 'timeline', label: '时间线' },
  { key: 'calendar', label: '日历' },
  { key: 'deliverables', label: '交付物' },
]

const weekDayLabel = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const today = computed(() => startOfDay(new Date()))
const weekDays = computed(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart.value, index)))
const weekLabel = computed(() => {
  const end = addDays(weekStart.value, 6)
  return `${weekStart.value.getMonth() + 1}月${weekStart.value.getDate()}日 – ${end.getMonth() + 1}月${end.getDate()}日`
})
const calendarTitle = computed(() => `${currentMonth.value.getFullYear()}年${currentMonth.value.getMonth() + 1}月`)
const viewTitle = computed(() => {
  return { timeline: '周时间线', calendar: '日历', deliverables: '交付物中心' }[view.value]
})
const viewSub = computed(() => {
  return {
    timeline: '按本周查看任务排期与依赖；日历看月度。',
    calendar: '整月查看任务排期，同一任务跨天使用同一颜色。',
    deliverables: '以列表统一查看所有 AI 任务产出的方案、草稿和写库结果。',
  }[view.value]
})
function getBodyContainer(): HTMLElement {
  return document.body
}

function startOfDay(date: Date): Date {
  const next = new Date(date)
  next.setHours(0, 0, 0, 0)
  return next
}

function addDays(date: Date, amount: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + amount)
  return next
}

function startOfWeek(date: Date): Date {
  const next = startOfDay(date)
  const offset = (next.getDay() + 6) % 7
  next.setDate(next.getDate() - offset)
  return next
}

function parseDate(value?: string): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function isSameDay(left: Date, right: Date): boolean {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth() && left.getDate() === right.getDate()
}

function daysBetween(left: Date, right: Date): number {
  return Math.round((startOfDay(left).getTime() - startOfDay(right).getTime()) / 86400000)
}

function formatDateLabel(date: Date): string {
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function formatTime(value?: string): string {
  if (!value) return '--:--:--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-CN', { hour12: false })
}

function colleagueName(roleKey?: string): string {
  if (!roleKey) return 'Leader 分配'
  return props.colleagues.find((colleague) => colleague.role_key === roleKey)?.name || roleKey
}

function missionStatusLabel(status: string): string {
  return props.behaviorConfig.mission?.status_meta?.[status]?.label || status || '排队中'
}

function assignmentStatusLabel(status?: string): string {
  const meta = props.behaviorConfig.mission?.assignment_status_meta?.[status || '']
  return meta?.label || status || '空闲'
}

function statusColor(status: string): string {
  return props.behaviorConfig.mission?.status_meta?.[status]?.color || '#9aa4b2'
}

function missionSpan(mission: OfficeMission): { start: Date; end: Date } {
  const start = parseDate(mission.created_at) || today.value
  const end = parseDate(mission.completed_at) || (mission.status === 'running' ? today.value : start)
  return { start, end }
}

function sourceLabel(source?: string): string {
  return (
    {
      portal_chat: '门户聊天',
      solution_assistant: '方案助手',
      office: 'AI 办公室',
      user_task: '用户创建',
    } as Record<string, string>
  )[source || 'office'] || source || 'AI 办公室'
}

function deliverableTitle(deliverable: OfficeDeliverable): string {
  return deliverable.title || deliverable.type || '交付物'
}

function deliverableContent(deliverable: OfficeDeliverable): string {
  return deliverable.content || deliverable.url || ''
}

function missionColor(mission: OfficeMission): string {
  return statusColor(mission.status)
}

function moveWeek(delta: number): void {
  weekStart.value = addDays(weekStart.value, delta * 7)
}

function moveMonth(delta: number): void {
  const next = new Date(currentMonth.value)
  next.setMonth(next.getMonth() + delta)
  currentMonth.value = next
}
const filteredMissions = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return props.missions.filter((mission) => {
    if (!keyword) return true
    const haystack = `${mission.prompt || ''} ${mission.mission_id || ''} ${colleagueName(mission.owner_role_key)} ${mission.status || ''}`.toLowerCase()
    return haystack.includes(keyword)
  })
})

const timelineRows = computed<TimelineRow[]>(() => {
  const rows: TimelineRow[] = []
  props.missions.forEach((mission) => {
    const color = missionColor(mission)
    const fallbackStart = parseDate(mission.created_at) || today.value
    const fallbackEnd = parseDate(mission.completed_at) || (mission.status === 'running' ? today.value : fallbackStart)
    const steps = mission.steps || []
    if (steps.length) {
      steps.forEach((step, index) => {
        const start = parseDate(step.started_at || step.assigned_at) || fallbackStart
        const end = parseDate(step.completed_at) || (step.assignment_status === 'done' ? start : today.value)
        rows.push({
          id: `${mission.mission_id}-${step.step_id || index}`,
          label: step.task || `步骤 ${index + 1}`,
          owner: colleagueName(step.role_key || step.completed_by || mission.owner_role_key),
          start,
          end,
          color,
          missionId: mission.mission_id,
        })
      })
    } else {
      rows.push({
        id: mission.mission_id,
        label: mission.prompt,
        owner: colleagueName(mission.owner_role_key),
        start: fallbackStart,
        end: fallbackEnd,
        color,
        missionId: mission.mission_id,
      })
    }
  })
  return rows
})

const visibleTimelineRows = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  const weekEnd = addDays(weekStart.value, 6)
  return timelineRows.value
    .filter((row) => {
      const haystack = `${row.label} ${row.owner}`.toLowerCase()
      const inWeek = startOfDay(row.start) <= weekEnd && startOfDay(row.end) >= startOfDay(weekStart.value)
      return inWeek && (!keyword || haystack.includes(keyword))
    })
    .sort((left, right) => left.start.getTime() - right.start.getTime())
})

function ganttBarStyle(row: TimelineRow): Record<string, string> {
  const startIdx = Math.max(0, daysBetween(row.start, weekStart.value))
  const endIdx = Math.min(6, daysBetween(row.end, weekStart.value))
  if (startIdx > 6 || endIdx < 0) return { display: 'none' }
  const left = (startIdx / 7) * 100
  const width = ((endIdx - startIdx + 1) / 7) * 100
  return { left: `${left}%`, width: `${width}%`, background: row.color }
}

const calendarCells = computed<CalendarCell[]>(() => {
  const year = currentMonth.value.getFullYear()
  const month = currentMonth.value.getMonth()
  const firstDay = new Date(year, month, 1)
  const offset = (firstDay.getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: CalendarCell[] = []
  for (let index = 0; index < offset; index += 1) {
    const date = new Date(year, month, 1 - offset + index)
    cells.push({ key: `lead-${index}`, day: date.getDate(), date, muted: true, missions: [] })
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(year, month, day)
    const missions = filteredMissions.value.filter((mission) => {
      const span = missionSpan(mission)
      return startOfDay(span.start) <= startOfDay(date) && startOfDay(date) <= startOfDay(span.end)
    })
    cells.push({ key: `day-${day}`, day, date, muted: false, missions })
  }
  const tail = (7 - (cells.length % 7)) % 7
  for (let index = 1; index <= tail; index += 1) {
    const date = new Date(year, month + 1, index)
    cells.push({ key: `tail-${index}`, day: date.getDate(), date, muted: true, missions: [] })
  }
  return cells
})

const deliverableRows = computed<DeliverableRow[]>(() => {
  const rows: DeliverableRow[] = []
  props.missions.forEach((mission) => {
    ;(mission.artifacts || []).forEach((artifact, index) => {
      rows.push({
        id: `${mission.mission_id}-artifact-${index}`,
        mission,
        deliverable: artifact as OfficeDeliverable,
      })
    })
    ;(mission.deliverables || []).forEach((deliverable, index) => {
      rows.push({ id: `${mission.mission_id}-m-${index}`, mission, deliverable })
    })
    ;(mission.steps || []).forEach((step) => {
      ;(step.deliverables || []).forEach((deliverable, index) => {
        rows.push({ id: `${mission.mission_id}-${step.step_id}-${index}`, mission, deliverable, sourceStep: step })
      })
    })
  })
  return rows
})

const filteredDeliverableRows = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return deliverableRows.value.filter((row) => {
    if (!keyword) return true
    const haystack = `${row.mission.prompt || ''} ${row.mission.mission_id || ''} ${deliverableTitle(row.deliverable)} ${deliverableContent(row.deliverable)}`.toLowerCase()
    return haystack.includes(keyword)
  })
})

const deliverableTaskCount = computed(() => new Set(filteredDeliverableRows.value.map((row) => row.mission.mission_id)).size)

const selectedMission = computed(() => props.missions.find((mission) => mission.mission_id === selectedMissionId.value) || null)

function openOpportunity(opportunityId: string) {
  if (!opportunityId) return
  router.push({ name: 'OpportunityDetail', params: { opportunityId } })
}

function isRealOpportunity(opportunityId?: string): boolean {
  const id = String(opportunityId || '').trim()
  if (!id) return false
  if (id.startsWith('m_')) return false
  return true
}

function openMission(missionId: string | null | undefined) {
  if (!missionId) return
  selectedMissionId.value = missionId
  detailOpen.value = true
}

function plansFromArtifact(artifact: any): Plan[] {
  const data = artifact?.data
  if (Array.isArray(data?.plans)) return data.plans as Plan[]
  if (Array.isArray(artifact?.plans)) return artifact.plans as Plan[]
  return []
}

function artifactViewFromArtifact(artifact: any): ArtifactViewData | null {
  const data = artifact?.data
  const bomScheme = data?.bom_scheme
  if (bomScheme && (artifact?.type === 'bom_scheme_draft' || artifact?.type === 'bom_scheme')) {
    return { entityType: 'bom_scheme', entity: bomScheme }
  }
  return null
}

function artifactSummary(artifact: any): string {
  const view = artifactViewFromArtifact(artifact)
  if (view?.entityType === 'bom_scheme') {
    const configs = Array.isArray(view.entity?.configs) ? view.entity.configs : []
    if (!configs.length) return '已生成 BOM 方案草稿'
    const total = configs.reduce((sum: number, cfg: any) => sum + Number(cfg.totals?.totalCost || 0), 0)
    return `${configs.length} 个配置页签 · 总价 ¥${total.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  const content = artifact?.content || artifact?.url
  return content ? String(content).slice(0, 120) : ''
}

function openArtifact(artifact: any) {
  artifactTitle.value = artifact?.title || artifact?.type || '产出物'
  artifactContent.value = artifact?.content || ''
  artifactPlans.value = plansFromArtifact(artifact)
  artifactView.value = artifactViewFromArtifact(artifact)
  artifactBomOpen.value = false
  artifactBomPlan.value = null
  artifactBomCfg.value = null
  artifactPreviewOpen.value = true
}

async function openArtifactBom(plan: Plan) {
  artifactBomPlan.value = plan
  artifactBomCfg.value = null
  artifactBomLoading.value = true
  artifactBomOpen.value = true
  try {
    artifactBomCfg.value = await buildPlanCfg(plan)
  } catch {
    artifactBomCfg.value = null
  } finally {
    artifactBomLoading.value = false
  }
}

function openCreate() {
  createForm.value = { prompt: '', owner_role_key: undefined, priority: 'medium' }
  createOpen.value = true
}

async function createMission() {
  const prompt = createForm.value.prompt.trim()
  if (!prompt) {
    message.warning('请填写任务目标')
    return
  }
  actionLoading.value = true
  try {
    const mission = await officeApi.createMission({
      prompt,
      owner_role_key: createForm.value.owner_role_key || null,
      priority: createForm.value.priority,
    })
    createOpen.value = false
    selectedMissionId.value = mission.mission_id
    emit('changed')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '创建任务失败')
  } finally {
    actionLoading.value = false
  }
}

function cancelSelected() {
  if (!selectedMissionId.value) return
  Modal.confirm({
    title: '取消当前任务？',
    content: '取消后任务步骤会停止，状态变为已取消。',
    okText: '取消任务',
    okType: 'danger',
    cancelText: '返回',
    onOk: () => executeAction(() => officeApi.cancelMission(selectedMissionId.value!), '任务已取消'),
  })
}

function retrySelected() {
  if (!selectedMissionId.value) return
  Modal.confirm({
    title: '重试当前任务？',
    content: '将基于当前任务目标重新下达。',
    okText: '重试',
    cancelText: '取消',
    onOk: () => executeAction(() => officeApi.retryMission(selectedMissionId.value!), '任务已重新下达'),
  })
}

function deleteSelected() {
  if (!selectedMissionId.value) return
  Modal.confirm({
    title: '删除当前任务？',
    content: '删除后任务和步骤记录都会移除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => executeAction(() => officeApi.deleteMission(selectedMissionId.value!), '任务已删除'),
  })
}

async function executeAction(action: () => Promise<any>, successText: string) {
  actionLoading.value = true
  try {
    await action()
    selectedMissionId.value = null
    message.success(successText)
    emit('changed')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '操作失败')
  } finally {
    actionLoading.value = false
  }
}

</script>
<style scoped>
.tc-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 12px;
  padding: 16px 18px 18px;
  overflow: hidden;
  color: var(--cpq-text-primary);
  background: var(--cpq-bg-primary);
}

.tc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.tc-heading {
  min-width: 0;
}

.tc-kicker {
  color: var(--cpq-accent-primary, #1677ff);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.tc-heading h2 {
  margin: 2px 0;
  font-size: 22px;
}

.tc-heading p {
  margin: 0;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.tc-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
}

.tc-search {
  width: 260px;
}

.tc-nav {
  display: flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 10px;
  background: var(--cpq-bg-secondary);
  width: max-content;
}

.tc-nav-btn {
  border: 0;
  border-radius: 7px;
  padding: 7px 14px;
  color: var(--cpq-text-secondary);
  background: transparent;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.tc-nav-btn.active {
  color: var(--cpq-accent-primary);
  background: var(--cpq-bg-card);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.tc-empty {
  padding: 22px 8px;
  color: var(--cpq-text-muted);
  font-size: 12px;
  text-align: center;
}

.td-meta,
.td-step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--cpq-text-muted);
  font-size: 11px;
}

.tc-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 999px;
  color: var(--status-color, var(--cpq-text-muted));
  background: color-mix(in srgb, var(--status-color, var(--cpq-text-muted)) 14%, transparent);
  font-size: 10px;
  font-weight: 800;
}

.tc-timeline,
.tc-calendar,
.tc-deliverables {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: 10px;
}

.tc-section-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.tc-section-title {
  color: var(--cpq-text-primary);
  font-size: 20px;
  font-weight: 800;
}

.tc-section-sub {
  margin-top: 4px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.tc-section-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tc-week-label {
  color: var(--cpq-text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.tc-gantt,
.tc-dv-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 12px;
  background: var(--cpq-bg-card);
}

.tc-gantt-scroll {
  min-width: 960px;
}

.tc-gantt-header,
.tc-gantt-row {
  display: grid;
  grid-template-columns: 190px repeat(7, minmax(96px, 1fr));
}

.tc-gantt-header {
  position: sticky;
  top: 0;
  z-index: 2;
  border-bottom: 1px solid var(--cpq-border-primary);
  background: var(--cpq-bg-secondary);
}

.tc-gantt-corner {
  padding: 12px 14px;
  border-right: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  font-weight: 800;
}

.tc-gantt-day {
  padding: 9px 0 7px;
  border-right: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-muted);
  font-size: 11px;
  text-align: center;
}

.tc-gantt-day b {
  display: block;
  margin-bottom: 2px;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.tc-gantt-day.today {
  background: color-mix(in srgb, var(--cpq-accent-primary) 8%, transparent);
}

.tc-gantt-day.today b {
  color: var(--cpq-accent-primary);
}

.tc-gantt-day.weekend {
  background: var(--cpq-bg-secondary);
}

.tc-gantt-row {
  min-height: 54px;
  border-bottom: 1px solid var(--cpq-border-primary);
}

.tc-gantt-label {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding: 11px 14px;
  border-right: 1px solid var(--cpq-border-primary);
  background: var(--cpq-bg-card);
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.tc-gantt-label b {
  color: var(--cpq-text-primary);
  font-size: 12px;
}

.tc-gantt-label small {
  color: var(--cpq-text-muted);
  font-size: 10px;
}

.tc-gantt-track {
  position: relative;
  grid-column: 2 / 9;
  min-height: 54px;
}

.tc-gantt-bar {
  position: absolute;
  top: 12px;
  height: 28px;
  overflow: hidden;
  border: 0;
  border-radius: 7px;
  padding: 0 8px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  text-overflow: ellipsis;
  cursor: pointer;
}

.tc-cal-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 12px;
  background: var(--cpq-bg-card);
}

.tc-cal-weekday {
  padding: 9px 12px;
  border-right: 1px solid var(--cpq-border-primary);
  border-bottom: 1px solid var(--cpq-border-primary);
  background: var(--cpq-bg-secondary);
  color: var(--cpq-text-muted);
  font-size: 11px;
  font-weight: 800;
  text-align: center;
}

.tc-cal-cell {
  min-height: 96px;
  padding: 6px;
  border-right: 1px solid var(--cpq-border-primary);
  border-bottom: 1px solid var(--cpq-border-primary);
  background: var(--cpq-bg-card);
}

.tc-cal-cell.muted {
  background: var(--cpq-bg-secondary);
}

.tc-cal-cell.today {
  background: color-mix(in srgb, var(--cpq-accent-primary) 8%, var(--cpq-bg-card));
}

.tc-cal-day-num {
  margin-bottom: 5px;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.tc-cal-cell.today .tc-cal-day-num b {
  color: var(--cpq-accent-primary);
}

.tc-cal-event {
  display: block;
  width: 100%;
  margin-bottom: 4px;
  overflow: hidden;
  border: 0;
  border-radius: 6px;
  padding: 3px 6px;
  color: #fff;
  font-size: 11px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.tc-dv-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.tc-dv-summary b {
  color: var(--cpq-text-primary);
  font-size: 13px;
}

.tc-dv-row {
  display: grid;
  grid-template-columns: minmax(240px, 1.5fr) minmax(220px, 1.3fr) 92px 92px 96px 110px;
  gap: 12px;
  align-items: center;
  width: 100%;
  min-width: 960px;
  padding: 12px 16px;
  border: 0;
  border-bottom: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-primary);
  background: transparent;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.tc-dv-row:hover {
  background: color-mix(in srgb, var(--cpq-accent-primary) 8%, transparent);
}

.tc-dv-head-row {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--cpq-bg-secondary);
  color: var(--cpq-text-secondary);
  font-size: 11px;
  font-weight: 800;
  cursor: default;
}

.tc-dv-head-row:hover {
  background: var(--cpq-bg-secondary);
}

.tc-dv-title-cell b,
.tc-dv-task-cell b {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tc-dv-title-cell b {
  margin-bottom: 4px;
  font-size: 13px;
}

.tc-dv-title-cell span,
.tc-dv-task-cell small {
  display: block;
  overflow: hidden;
  color: var(--cpq-text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.td-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.td-label {
  color: var(--cpq-text-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.td-value {
  color: var(--cpq-text-primary);
  font-size: 14px;
  line-height: 1.55;
}

.td-meta {
  flex-wrap: wrap;
}

.td-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 18px;
}

.td-report {
  padding: 10px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 10px;
  background: var(--cpq-bg-secondary);
}

.td-report-title {
  margin-bottom: 6px;
  color: var(--cpq-text-primary);
  font-size: 13px;
  font-weight: 800;
}

.td-report-content {
  color: var(--cpq-text-muted);
  font-size: 12px;
  white-space: pre-wrap;
}

.td-artifact-plans {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.td-step {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border-left: 3px solid color-mix(in srgb, var(--cpq-accent-primary) 70%, transparent);
  background: var(--cpq-bg-secondary);
}

.td-step-task {
  color: var(--cpq-text-primary);
  font-size: 13px;
}

.td-step-result {
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.td-empty {
  padding: 22px 8px;
  color: var(--cpq-text-muted);
  font-size: 12px;
  text-align: center;
}

.tc-modal-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tc-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.tc-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}
</style>

