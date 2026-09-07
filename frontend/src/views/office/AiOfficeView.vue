<template>
  <div class="ai-office-shell">
    <header class="office-toolbar">
      <a-dropdown :trigger="['click']">
        <button type="button" class="room-picker">
          <span class="room-picker-dot" :style="{ background: teamColor }"></span>
          <span class="room-picker-name">{{ activeRoomMeta.name || 'AI 团队' }}</span>
          <DownOutlined />
        </button>
        <template #overlay>
          <a-menu class="room-picker-menu" @click="onRoomMenuClick">
            <a-menu-item v-for="room in rooms" :key="room.id">
              <span class="room-picker-dot" :style="{ background: room.color || '#1677ff' }"></span>
              <span>{{ room.name || room.id }}</span>
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>

      <div class="office-actions">
        <span class="connection-pill" :class="{ online: connected }">
          <i></i>{{ connected ? 'LIVE' : 'OFFLINE' }}
        </span>
        <a-button v-if="canManageOffice" type="primary" @click="manageOpen = true">
          <template #icon><SettingOutlined /></template>
          Manage Teams
        </a-button>
        <a-button @click="governanceOpen = true">治理审批</a-button>
      </div>
    </header>

    <div class="office-workspace">
      <aside class="office-sidebar">
        <section class="sidebar-section sidebar-recent-card sidebar-mission-card">
          <div class="sidebar-section-head">
            <div>
              <div class="sidebar-section-title">任务看板</div>
              <div class="sidebar-section-desc">按状态跟踪任务与负责人</div>
            </div>
            <a-button type="link" size="small" @click="openMissionPanel">打开看板</a-button>
          </div>
          <div class="mission-preview-stats">
            <button
              v-for="stat in missionPreviewStats"
              :key="stat.key"
              class="mission-preview-stat"
              type="button"
              @click="openMissionPanel"
            >
              <strong>{{ stat.value }}</strong>
              <span>{{ stat.label }}</span>
            </button>
          </div>
          <div v-if="!missions.length" class="sidebar-empty">暂无任务</div>
          <div v-if="missionError" class="sidebar-error">{{ missionError }}</div>
          <div
            v-for="mission in missions.slice(0, 4)"
            :key="mission.mission_id"
            class="sidebar-mission-item"
            @click="openMissionPanel"
          >
            <span class="mission-status" :class="mission.status">{{ missionStatusLabel(mission.status) }}</span>
            <div class="sidebar-mission-copy">
              <div class="sidebar-mission-prompt">{{ mission.prompt }}</div>
              <div class="sidebar-mission-time">{{ colleagueName(mission.owner_role_key) }} · {{ formatEventTime(mission.created_at ? new Date(mission.created_at).getTime() : undefined) }}</div>
            </div>
          </div>
        </section>
      </aside>

      <main class="office-map-panel">
        <div class="map-toolbar">
          <div class="map-title">
            <strong>办公区</strong>
            <span>{{ roomColleagues.length }} 位 AI 同事</span>
          </div>
          <div class="map-legend">
            <span v-for="(meta, status) in statusMetaEntries" :key="status">
              <i class="legend-dot" :style="{ background: meta.color || '#9aa4b2' }"></i>{{ meta.label || status }}
            </span>
            <a-button v-if="canManageOffice" size="small" type="primary" ghost class="legend-reset-btn" @click="onResetOfficeSample">恢复样板</a-button>
          </div>
        </div>

        <Office3DCanvas
          :colleagues="roomColleagues"
          :status-map="statusMap"
          :selected-role-key="selectedRoleKey"
          :office-config="officeConfig"
          :behavior-config="behaviorConfig"
          :editable="canManageOffice"
          @select="selectColleague"
          @save-config="onSaveOfficeConfig"
        />
        <div v-if="!roomColleagues.length" class="office-empty-state">
          暂无 AI 同事，请在 Manage Teams 中添加或切换团队。
        </div>
      </main>

      <aside class="inspector-panel">
        <template v-if="selectedColleague">
          <div class="inspector-head">
            <div class="inspector-avatar" :style="{ background: deskColor(selectedColleague) }">
              <img v-if="selectedColleague.avatar_url" :src="selectedColleague.avatar_url" alt="" />
              <span v-else>{{ avatarInitial(selectedColleague.name) }}</span>
            </div>
            <div class="inspector-identity">
              <div class="inspector-name">{{ selectedColleague.name || selectedColleague.role_key }}</div>
              <div class="inspector-role">{{ selectedColleague.role_key }}</div>
            </div>
            <span class="status-pill" :style="statusPillStyle(selectedStatus.status)">{{ statusText(selectedStatus.status) }}</span>
          </div>

          <div class="inspector-sections">
            <div class="inspector-section inspector-chat-section">
              <OfficeColleagueChatPanel
                :colleague="selectedColleague"
                :context="officeChatContext"
                :context-summary="officeContextSummary"
              />
            </div>
          </div>
        </template>

        <div v-else class="inspector-empty">
          点击办公室中的 AI 同事查看详情
        </div>
      </aside>
    </div>

    <Teleport to="body">
      <Transition name="office-fade">
        <div v-if="manageOpen" class="manager-backdrop manager-backdrop--full" @click.self="manageOpen = false">
          <section class="manager-shell">
            <AiOfficeManagement
              :colleagues="colleagues"
              :rooms="rooms"
              :team-meta="teamMeta"
              :layout-nodes="layoutNodes"
              :layout-edges="layoutEdges"
              :office-config="officeConfig"
              :behavior-config="behaviorConfig"
              :initial-role-key="selectedRoleKey"
              :lead-role-key="teamGraph?.lead_role_key || null"
              @close="manageOpen = false"
              @saved="onTeamSaved"
            />
          </section>
        </div>
      </Transition>

      <Transition name="office-fade">
        <div v-if="governanceOpen" class="manager-backdrop" @click.self="governanceOpen = false">
          <section class="manager-shell gov-shell">
            <header class="gov-shell-head">
              <span>治理与审批</span>
              <a-button type="text" @click="governanceOpen = false">关闭</a-button>
            </header>
            <GovernancePanel />
          </section>
        </div>
      </Transition>

      <Transition name="office-fade">
        <div v-if="missionPanelOpen" class="manager-backdrop mission-backdrop" @click.self="missionPanelOpen = false">
          <section class="manager-shell mission-command-shell">
            <TaskBoard
              :missions="missions"
              :colleagues="colleagues"
              :behavior-config="behaviorConfig"
              :loading="missionLoading"
              @close="missionPanelOpen = false"
              @refresh="loadMissions"
              @changed="loadMissions"
            />
          </section>
        </div>
      </Transition>

    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onActivated, onDeactivated, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { DownOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { AssistantContext } from '@/api/assistant'
import { officeApi, type BehaviorConfig, type OfficeColleagueStatus, type OfficeConfig, type OfficeMission } from '@/api/office'
import { normalizeOfficeConfig } from '@/composables/officeLayout'
import { useAssistantContext } from '@/composables/assistantContext'
import { useOfficeSocket } from '@/composables/useOfficeSocket'
import AiOfficeManagement from './AiOfficeManagement.vue'
import GovernancePanel from './GovernancePanel.vue'
import Office3DCanvas from './Office3DCanvas.vue'
import OfficeColleagueChatPanel from './OfficeColleagueChatPanel.vue'
import TaskBoard from './TaskBoard.vue'

defineOptions({ name: 'AiOfficeView' })

const teamMeta = ref<{ name?: string; description?: string; color?: string }>({})
const colleagues = ref<any[]>([])
const rooms = ref<any[]>([])
const activeRoomId = ref('default')
const layoutNodes = ref<any[]>([])
const layoutEdges = ref<any[]>([])
const officeConfig = ref<OfficeConfig>({})
const teamGraph = ref<{ lead_role_key?: string; subagent_role_keys?: string[] }>({})
const behaviorConfig = ref<BehaviorConfig>({})
const manageOpen = ref(false)
const governanceOpen = ref(false)
const selectedRoleKey = ref<string | null>(null)
const missions = ref<OfficeMission[]>([])
const missionPanelOpen = ref(false)
const missionLoading = ref(false)
const missionError = ref('')
let missionPollTimer: ReturnType<typeof setInterval> | null = null

const auth = useAuthStore()
const canManageOffice = computed(() => auth.can('ai.office.manage'))
const route = useRoute()
const { summarize: summarizeAssistantContext } = useAssistantContext()
const officeContextSummary = ref('')
const officeChatContext = computed<AssistantContext>(() => ({
  opportunityId: (route.query.opportunityId as string) || null,
  quotationId: (route.query.quotationId as string) || null,
}))

const { statusMap, connected, connect, disconnect } = useOfficeSocket()

const emptyStatus: OfficeColleagueStatus = {
  type: 'colleague_status',
  role_key: '',
  status: 'idle',
  activity: '',
  message: '',
}

const activeRoom = computed(() => rooms.value.find((room) => room.id === activeRoomId.value) || rooms.value[0] || null)
const activeRoomMeta = computed(() => activeRoom.value || teamMeta.value)
const roomColleagues = computed(() => {
  const roleKeys = activeRoom.value?.role_keys || []
  if (!roleKeys.length) return colleagues.value
  const allowed = new Set(roleKeys)
  return colleagues.value.filter((colleague) => allowed.has(colleague.role_key))
})
const teamColor = computed(() => activeRoomMeta.value.color || '#1677ff')
const selectedColleague = computed(() =>
  roomColleagues.value.find((c) => c.role_key === selectedRoleKey.value) || null,
)
const selectedStatus = computed(() =>
  selectedRoleKey.value ? statusFor(selectedRoleKey.value) : emptyStatus,
)

watch(
  roomColleagues,
  (list) => {
    if (list.length && !list.find((c) => c.role_key === selectedRoleKey.value)) {
      selectedRoleKey.value = list[0].role_key
    }
  },
  { immediate: true },
)

function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

function deskColor(colleague: any): string {
  return colleague?.color || '#1677ff'
}

function statusFor(roleKey: string): OfficeColleagueStatus {
  return statusMap.value[roleKey] || { ...emptyStatus, role_key: roleKey }
}

const statusMetaEntries = computed(() => behaviorConfig.value.status_meta || {})
const missionPreviewStats = computed(() => [
  { key: 'all', label: '全部', value: missions.value.length },
  { key: 'queued', label: '排队中', value: missions.value.filter((mission) => mission.status === 'queued').length },
  { key: 'running', label: '执行中', value: missions.value.filter((mission) => mission.status === 'running').length },
  { key: 'done', label: '已完成', value: missions.value.filter((mission) => mission.status === 'done').length },
])

function behaviorStatusMeta(status: string) {
  return statusMetaEntries.value[status] || {}
}

function statusText(status: string): string {
  return behaviorStatusMeta(status).label || status || '空闲'
}

function statusPillStyle(status: string) {
  const color = behaviorStatusMeta(status).color || '#9aa4b2'
  return {
    color,
    borderColor: color,
    background: `${color}1a`,
  }
}


function selectColleague(roleKey: string) {
  selectedRoleKey.value = roleKey
}

function formatEventTime(ts?: number): string {
  if (!ts) return '--:--:--'
  return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
}

async function loadConfig() {
  try {
    const data = await officeApi.teamConfig()
    teamMeta.value = data.team_meta || {}
    colleagues.value = Array.isArray(data.colleagues) ? data.colleagues : []
    rooms.value = Array.isArray(data.rooms) ? data.rooms : []
    if (rooms.value.length && !rooms.value.some((room) => room.id === activeRoomId.value)) {
      activeRoomId.value = rooms.value[0].id
    }
    layoutNodes.value = Array.isArray(data.layout?.nodes) ? data.layout.nodes : []
    layoutEdges.value = Array.isArray(data.layout?.edges) ? data.layout.edges : []
    officeConfig.value = normalizeOfficeConfig(data.layout?.office || {})
    teamGraph.value = data.layout?.team_graph || {}
    behaviorConfig.value = data.behavior || {}
  } catch (error: any) {
    colleagues.value = []
    message.error(error?.response?.data?.detail || 'AI 团队配置加载失败，请重新登录后再试')
  }
}

async function onSaveOfficeConfig(config: OfficeConfig) {
  try {
    await officeApi.updateLayout({ office: config })
    officeConfig.value = normalizeOfficeConfig(config)
    message.success('空间已保存')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '空间保存失败')
  }
}

async function onResetOfficeSample() {
  try {
    const res = await officeApi.resetOfficeSample()
    officeConfig.value = normalizeOfficeConfig(res.layout?.office || {})
    message.success('已恢复为默认精装修样板办公室')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '恢复样板失败')
  }
}

function onRoomMenuClick({ key }: { key: string | number }) {
  activeRoomId.value = String(key)
}

function colleagueName(roleKey?: string): string {
  if (!roleKey) return 'AI 团队'
  return colleagues.value.find((colleague) => colleague.role_key === roleKey)?.name || roleKey
}

function missionStatusLabel(status: string): string {
  return behaviorConfig.value.mission?.status_meta?.[status]?.label || status || '排队中'
}

async function loadMissions() {
  missionLoading.value = true
  try {
    const data = await officeApi.listMissions(20)
    missions.value = data.missions || []
    missionError.value = ''
  } catch (error: any) {
    missions.value = []
    missionError.value = error?.response?.data?.detail || error?.message || '任务加载失败，请重新登录后再试'
  } finally {
    missionLoading.value = false
  }
}

function startMissionPolling() {
  if (missionPollTimer) return
  missionPollTimer = setInterval(() => {
    // 页面不可见时不轮询，避免后台空跑造成网络与重绘开销。
    if (document.visibilityState !== 'visible') return
    loadMissions()
  }, 4000)
}

function openMissionPanel() {
  missionPanelOpen.value = true
}

async function onTeamSaved() {
  await loadConfig()
}

async function refreshOfficeContext() {
  try {
    const parts: string[] = []
    const providerSummary = await summarizeAssistantContext()
    if (providerSummary) parts.push(providerSummary)
    if (route.query.opportunityId) parts.push(`当前商机：${route.query.opportunityId}`)
    if (route.query.quotationId) parts.push(`当前报价单：${route.query.quotationId}`)
    officeContextSummary.value = parts.join('\n\n')
  } catch {
    officeContextSummary.value = ''
  }
}

watch(
  () => [route.query.opportunityId, route.query.quotationId],
  () => refreshOfficeContext(),
)

onMounted(() => {
  connect()
  loadConfig()
  loadMissions()
  startMissionPolling()
  refreshOfficeContext()
})

onBeforeUnmount(() => {
  if (missionPollTimer) {
    clearInterval(missionPollTimer)
    missionPollTimer = null
  }
})

// KeepAlive：切走时断 WS + 停轮询，切回时重连并刷新，避免后台连接泄漏
let _aiOfficeActivated = false
onActivated(() => {
  if (!_aiOfficeActivated) {
    _aiOfficeActivated = true
    return
  }
  connect()
  loadConfig()
  loadMissions()
  startMissionPolling()
  refreshOfficeContext()
})
onDeactivated(() => {
  disconnect()
  if (missionPollTimer) {
    clearInterval(missionPollTimer)
    missionPollTimer = null
  }
})
</script>

<style scoped>
.ai-office-shell {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--cpq-bg-primary);
  color: var(--cpq-text-primary);
  overflow: hidden;
}

.office-toolbar {
  height: 60px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 20px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.04));
}

.room-picker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
  cursor: pointer;
  transition: 0.2s ease;
}

.room-picker:hover {
  border-color: color-mix(in srgb, var(--cpq-accent-primary, #1677ff) 55%, transparent);
  background: var(--cpq-overlay-w10, rgba(255,255,255,0.10));
}

.room-picker-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.room-picker-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 800;
}

.room-picker :deep(.anticon) {
  font-size: 10px;
  color: var(--cpq-text-muted);
}

.office-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.connection-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

.connection-pill i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
}

.connection-pill.online {
  color: var(--cpq-color-success, #52c9a0);
}

.connection-pill.online i {
  background: var(--cpq-color-success, #52c9a0);
  box-shadow: 0 0 8px var(--cpq-color-success, #52c9a0);
}

/* Three-zone workspace: center map + right inspector */
.office-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}


/* Left command / colleagues sidebar */
.office-sidebar {
  width: 292px;
  flex-shrink: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  border-right: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.04));
}

.office-sidebar::-webkit-scrollbar {
  width: 8px;
}

.office-sidebar::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--cpq-overlay-w10, rgba(255,255,255,0.12));
}

.office-sidebar::-webkit-scrollbar-thumb:hover {
  background: var(--cpq-overlay-w15, rgba(255,255,255,0.18));
}

.sidebar-section {
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 14px;
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.04));
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.05);
}

.sidebar-section {
  padding: 14px;
}

.sidebar-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.sidebar-section-title {
  font-size: 13px;
  font-weight: 800;
  color: var(--cpq-text-primary);
}

.sidebar-section-desc {
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--cpq-text-muted);
}

.sidebar-empty {
  padding: 16px 10px;
  border-radius: 10px;
  font-size: 12px;
  color: var(--cpq-text-muted);
  text-align: center;
  background: var(--cpq-overlay-w4, rgba(255,255,255,0.04));
}

.sidebar-mission-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.sidebar-mission-item:hover {
  border-color: var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
}

.sidebar-mission-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.sidebar-mission-prompt {
  font-size: 12px;
  line-height: 1.35;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-mission-time {
  font-size: 10px;
  color: var(--cpq-text-muted);
}

.mission-preview-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin: 4px 0 8px;
}

.mission-preview-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 6px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  color: var(--cpq-text-muted);
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
  text-align: left;
}

.mission-preview-stat strong {
  color: var(--cpq-text-primary);
  font-size: 15px;
  font-weight: 800;
}

.mission-preview-stat span {
  font-size: 10px;
}

.sidebar-colleagues {
  padding-bottom: 12px;
}

.sidebar-colleague {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px;
  border-radius: 11px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.sidebar-colleague:hover {
  border-color: var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
}

.sidebar-colleague.active {
  border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.08));
}

.sidebar-colleague-dot {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 10px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.sidebar-colleague-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar-colleague-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-colleague-role {
  font-size: 10px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-colleague-status {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

.office-empty-state {
  position: absolute;
  inset: 56px 0 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--cpq-text-muted);
  font-size: 13px;
  text-align: center;
  padding: 24px;
  pointer-events: none;
}

.office-map-panel {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--cpq-bg-primary);
}

.map-toolbar {
  height: 42px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 18px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.04));
  font-size: 12px;
  color: var(--cpq-text-secondary);
}

.map-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.map-title strong {
  color: var(--cpq-text-primary);
  font-size: 13px;
}

.map-title span {
  color: var(--cpq-text-muted);
}

.map-legend {
  display: flex;
  align-items: center;
  gap: 10px;
}

.map-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
}

.legend-reset-btn {
  margin-left: 10px;
}

.mission-command-bar {
  min-height: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.04));
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.03));
}

.mission-input {
  flex: 1;
  min-width: 0;
}

.mission-list {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  font-size: 11px;
  color: var(--cpq-text-secondary);
}

.mission-empty {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--cpq-text-muted);
}

.mission-item {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
  white-space: nowrap;
}

.mission-status {
  flex-shrink: 0;
  font-weight: 700;
  color: var(--cpq-accent-primary, #1677ff);
}

.mission-status.done { color: var(--cpq-color-success, #52c9a0); }
.mission-status.failed { color: var(--cpq-accent-danger, #ff4d4f); }
.mission-status.cancelled { color: var(--cpq-text-muted); }

.mission-prompt {
  overflow: hidden;
  text-overflow: ellipsis;
}

.manager-shell.mission-command-shell {
  width: min(1180px, calc(100vw - 48px));
  height: min(780px, calc(100vh - 48px));
  border: 1px solid color-mix(in srgb, var(--cpq-border-secondary, rgba(255,255,255,0.10)) 92%, transparent);
  border-radius: 24px;
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--cpq-bg-elevated, rgba(255,255,255,0.04)) 72%, transparent), transparent 45%),
    color-mix(in srgb, var(--cpq-bg-primary, #0b1020) 78%, transparent);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.32), 0 0 0 1px rgba(255, 255, 255, 0.03) inset;
  backdrop-filter: blur(26px) saturate(150%);
  -webkit-backdrop-filter: blur(26px) saturate(150%);
}

.manager-backdrop.mission-backdrop {
  background: rgba(8, 12, 24, 0.36);
  backdrop-filter: blur(16px);
}

.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
}

.legend-dot.working { background: var(--cpq-accent-primary, #1677ff); }
.legend-dot.waiting { background: var(--cpq-accent-warning, #fa8c16); }
.legend-dot.error { background: var(--cpq-accent-danger, #ff4d4f); }
.legend-dot.idle { background: var(--cpq-text-muted); }

.status-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 9px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

/* Right inspector */
.inspector-panel {
  width: 420px;
  flex-shrink: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  border-left: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.04));
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.inspector-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.inspector-avatar {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
  font-weight: 800;
  overflow: hidden;
  flex-shrink: 0;
}

.inspector-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.inspector-identity {
  min-width: 0;
  flex: 1;
}

.inspector-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.inspector-role {
  margin-top: 3px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  font-family: ui-monospace, monospace;
}

.inspector-sections {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inspector-section {
  padding: 12px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.03));
}
.inspector-chat-section {
  flex: 1;
  min-height: 0;
  display: flex;
  padding: 0;
  border: 0;
  background: transparent;
}

.inspector-empty {
  margin: auto;
  font-size: 13px;
  color: var(--cpq-text-muted);
  text-align: center;
}

/* Manage Teams full-screen overlay */
.manager-backdrop {
  position: fixed;
  inset: 0;
  z-index: 900;
  padding: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 8, 16, 0.52);
  backdrop-filter: blur(10px);
}

.gov-shell {
  width: min(880px, 100%);
}

.gov-shell-head {
  padding: 0 16px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.10));
  font-size: 15px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.manager-shell {
  width: 100%;
  height: 100%;
  min-height: 0;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.10));
  border-radius: 18px;
  background: var(--cpq-bg-primary);
  box-shadow: 0 30px 80px rgba(0,0,0,0.35);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Manage Teams over-the-top: use the entire viewport so the Open3D canvas is truly full-screen. */
.manager-backdrop--full {
  padding: 0;
}

.manager-backdrop--full .manager-shell {
  border-radius: 0;
}

.office-fade-enter-active,
.office-fade-leave-active {
  transition: opacity .2s ease;
}

.office-fade-enter-from,
.office-fade-leave-to {
  opacity: 0;
}

@media (max-width: 860px) {
  .office-toolbar {
    padding: 0 12px;
    flex-wrap: wrap;
    gap: 8px;
  }

  .room-picker {
    width: 100%;
    max-width: none;
  }

  .office-actions {
    margin-left: auto;
  }

  .connection-pill {
    display: none;
  }

  .office-workspace {
    flex-direction: column;
    overflow: auto;
  }

  .office-map-panel {
    min-height: 460px;
  }


  .inspector-panel {
    width: 100%;
    border-left: none;
    border-top: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  }



  .map-toolbar {
    align-items: flex-start;
    flex-direction: column;
    height: auto;
    padding: 10px 12px;
    gap: 8px;
  }

  .manager-backdrop {
    padding: 0;
  }

  .manager-shell {
    border-radius: 0;
    border: none;
  }
}
</style>
