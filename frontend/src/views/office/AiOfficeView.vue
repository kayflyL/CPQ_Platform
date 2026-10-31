<template>
  <div class="ai-office-shell">
    <!-- 手机端专用顶栏（桌面无顶栏：三栏布局，命令在右栏） -->
    <header v-if="isMobile" class="office-toolbar">
      <button class="ws-back" title="返回桌面" @click="goDesktop">
        <ArrowLeftOutlined />
      </button>

      <div class="office-actions">
        <span class="connection-pill" :class="{ online: connected }">
          <i></i><span class="connection-pill-text">{{ connected ? 'LIVE' : 'OFFLINE' }}</span>
        </span>
        <!-- 主按钮双端统一 Manage Teams；手机端任务看板收进右侧「更多」菜单（红点=有运行中任务） -->
        <a-button v-if="canOpenOfficeManagement" type="primary" @click="manageOpen = true">
          <template #icon><SettingOutlined /></template>
          Manage Teams
        </a-button>
        <a-button v-if="!isMobile" @click="governanceOpen = true">日志审批</a-button>
        <a-dropdown v-if="isMobile" :trigger="['click']" placement="bottomRight">
          <button type="button" class="of-more">
            <EllipsisOutlined />
            <i v-if="runningMissionCount" class="of-more-dot"></i>
          </button>
          <template #overlay>
            <a-menu @click="onMobileMoreMenu">
              <a-menu-item key="tasks"><UnorderedListOutlined /> 任务看板</a-menu-item>
              <a-menu-item key="gov"><AuditOutlined /> 日志审批</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
    </header>

    <div v-if="!isMobile" class="office-workspace">
      <!-- 左栏：回桌面 + 任务看板（平铺全高，无玻璃罩框） -->
      <aside class="office-sidebar">
        <button class="ws-back" title="返回桌面" @click="goDesktop">
          <ArrowLeftOutlined /><span>桌面</span>
        </button>

        <div class="board-head">
          <div class="board-head-text">
            <div class="board-title">任务看板</div>
            <div class="board-desc">按状态跟踪任务与负责人</div>
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
          v-for="mission in missions.slice(0, 6)"
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
      </aside>

      <!-- 中栏：3D 办公区（满高；图例/编辑为画布浮动件；悬停同事 → 头顶卡） -->
      <main class="office-map-panel">
        <div class="map-float">
          <div class="map-title">
            <strong>办公区</strong>
            <span>{{ roomColleagues.length }} 位 AI 同事</span>
          </div>
          <div class="map-legend">
            <span v-for="(meta, status) in statusMetaEntries" :key="status">
              <i class="legend-dot" :style="{ background: meta.color || '#9aa4b2' }"></i>{{ meta.label || status }}
            </span>
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
          @deselect="closeRoleCard"
          @open-mission="onOpenMission"
          @save-config="onSaveOfficeConfig"
        />
        <OfficeHoverCard
          :colleague="hoverColleague"
          :status="hoverStatus"
          :stats="hoverStats"
          :color="hoverColor"
          :x="hoverCard?.x || 0"
          :y="hoverCard?.y || 0"
          @chat="hoverChat"
          @profile="hoverArchive"
        />
        <div v-if="!roomColleagues.length" class="office-empty-state">
          暂无 AI 同事，请在 Manage Teams 中添加或切换团队。
        </div>
      </main>

      <!-- 右栏：办公室状态栏（命令 + 今日 + 同事名册 + 房间 + 最近动态） -->
      <aside class="office-rail">
        <div class="rail-cmds">
          <span class="connection-pill" :class="{ online: connected }">
            <i></i><span class="connection-pill-text">{{ connected ? 'LIVE' : 'OFFLINE' }}</span>
          </span>
          <a-button v-if="canOpenOfficeManagement" type="primary" size="small" @click="manageOpen = true">
            <template #icon><SettingOutlined /></template>
            Manage Teams
          </a-button>
          <a-button size="small" @click="governanceOpen = true">日志审批</a-button>
        </div>

        <div class="rail-sec">
          <div class="rail-k">今日</div>
          <div class="rail-big od-num">{{ workingCount }}<small>/ {{ roomColleagues.length }} 人在工作</small></div>
          <div class="rail-bar">
            <i v-for="seg in railStatusSegs" :key="seg.status" :style="{ background: seg.color, flex: seg.count }"></i>
          </div>
          <div class="rail-bar-legend">
            <span v-for="seg in railStatusSegs" :key="seg.status"><i :style="{ background: seg.color }"></i>{{ seg.label }} {{ seg.count }}</span>
          </div>
        </div>

        <div class="rail-sec">
          <div class="rail-k">同事名册 <span class="rail-n">{{ roomColleagues.length }}</span></div>
          <div class="rail-list">
            <div
              v-for="c in roomColleagues"
              :key="c.role_key"
              class="rail-item"
              :class="{ 'is-active': hoverCard?.roleKey === c.role_key }"
              @click="showRailCard(c, $event)"
            >
              <span class="rail-item-av" :style="{ background: deskColor(c) }">
                <img v-if="c.avatar_url" :src="c.avatar_url" alt="" />
                <span v-else>{{ avatarInitial(c.name) }}</span>
              </span>
              <span class="rail-item-main">
                <b>{{ c.name || c.role_key }}</b>
                <small><i :style="{ background: avatarDotColor(c) }"></i>{{ statusText(statusFor(c.role_key).status) }}</small>
              </span>
              <button class="rail-chat" title="聊天" @click.stop="openChat(c.role_key)">聊天</button>
            </div>
            <div v-if="!roomColleagues.length" class="sidebar-empty">暂无同事</div>
          </div>
        </div>

        <div class="rail-sec">
          <div class="rail-k">房间</div>
          <div class="rail-list">
            <button
              v-for="room in viewRooms"
              :key="room.id"
              type="button"
              class="rail-item rail-room"
              :class="{ 'is-active': room.id === activeRoomId }"
              @click="activeRoomId = room.id"
            >
              <span class="rail-item-main"><b>{{ room.name || room.id }}</b></span>
              <span v-if="room.id === activeRoomId" class="rail-cur">当前</span>
            </button>
            <div v-if="!viewRooms.length" class="sidebar-empty">暂无房间</div>
          </div>
          <button class="rail-chat rail-chat--block" @click="openChat('room')">团队群聊 →</button>
        </div>
      </aside>
    </div>

    <!-- =================== 手机端：3D 全屏 + 同事头像行 =================== -->
    <template v-if="isMobile">
      <div class="m-stage">
        <Office3DCanvas
          :colleagues="roomColleagues"
          :status-map="statusMap"
          :selected-role-key="selectedRoleKey"
          :office-config="officeConfig"
          :behavior-config="behaviorConfig"
          :editable="false"
          @select="selectColleague"
          @open-mission="onOpenMission"
        />
        <div class="m-legend">
          <span v-for="(meta, status) in statusMetaEntries" :key="status">
            <i :style="{ background: meta.color || '#9aa4b2' }"></i>{{ meta.label || status }}
          </span>
        </div>
        <div v-if="!roomColleagues.length" class="m-empty">暂无 AI 同事，请在 Manage Teams 中添加或切换团队。</div>
      </div>

      <div class="m-peoplebar">
        <div class="m-people-row">
          <button
            v-for="c in roomColleagues"
            :key="c.role_key"
            type="button"
            class="m-pav"
            :class="{ 'is-active': selectedRoleKey === c.role_key }"
            @click="openChat(c.role_key)"
          >
            <span class="m-av" :style="{ background: deskColor(c) }">
              <img v-if="c.avatar_url" :src="c.avatar_url" alt="" />
              <span v-else>{{ avatarInitial(c.name) }}</span>
            </span>
            <span class="m-nm">{{ c.name || c.role_key }}</span>
            <span class="m-st" :style="{ background: avatarDotColor(c) }"></span>
          </button>
          <span v-if="!roomColleagues.length" class="m-people-empty">暂无同事</span>
        </div>
      </div>

      <!-- 任务看板全屏层（TaskBoard 复用；甘特/清单 min-width 960，全屏 + 双向滚动） -->
      <Transition name="m-chatup">
        <div v-if="tasksOpen" class="m-tasklayer">
          <div class="m-taskscroll">
            <TaskBoard
              :missions="missions"
              :colleagues="colleagues"
              :behavior-config="behaviorConfig"
              :loading="missionLoading"
              :focus-mission-id="missionFocus?.missionId || null"
              :focus-role-key="missionFocus?.roleKey || null"
              @close="closeTasksBoard"
              @refresh="loadMissions"
              @changed="loadMissions"
            />
          </div>
        </div>
      </Transition>
    </template>

    <!-- 同事档案弹窗（独立挂载；工作区卡片 [档案] 直达，不经过 Manage Teams 全屏壳） -->
    <EmployeeManager
      v-if="archiveRoleKey"
      :colleagues="colleagues"
      :initial-role-key="archiveRoleKey"
      modal-only
      @close="archiveRoleKey = null"
      @saved="loadConfig"
    />

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
              <span>日志与审批</span>
              <a-button type="text" @click="governanceOpen = false">关闭</a-button>
            </header>
            <GovernancePanel :colleagues="colleagues" />
          </section>
        </div>
      </Transition>

      <Transition name="office-fade">
        <div v-if="missionPanelOpen" class="manager-backdrop mission-backdrop" @click.self="closeTasksBoard">
          <section class="manager-shell mission-command-shell">
            <TaskBoard
              :missions="missions"
              :colleagues="colleagues"
              :behavior-config="behaviorConfig"
              :loading="missionLoading"
              :focus-mission-id="missionFocus?.missionId || null"
              :focus-role-key="missionFocus?.roleKey || null"
              @close="closeTasksBoard"
              @refresh="loadMissions"
              @changed="loadMissions"
            />
          </section>
        </div>
      </Transition>

    </Teleport>

    <!-- 浮动 AI 同事（办公室常驻层）：拆独立门面前由 CPQ 布局壳代挂，门面独立后归位办公室本体。
         全屏层（Manage Teams 等）挂 body 类时照旧让位（AssistantFloatingButton 自带该 CSS） -->
    <template v-if="auth.chatRolesAllowed && auth.isAuthenticated">
      <AssistantFloatingButton v-model:open="assistantOpen" :model-key="petModel.activePetModel" />
      <AssistantPanel ref="assistantPanelRef" v-model:open="assistantOpen" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onActivated, onDeactivated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { SettingOutlined, EllipsisOutlined, UnorderedListOutlined, AuditOutlined, ArrowLeftOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { officeApi, type BehaviorConfig, type OfficeColleagueStatus, type OfficeConfig, type OfficeMission } from '@/api/office'
import { normalizeOfficeConfig } from '@/composables/officeLayout'
import { useOfficeProfile } from '@/composables/officeProfile'
import { useOfficeSocket } from '@/composables/useOfficeSocket'
import AiOfficeManagement from './AiOfficeManagement.vue'
import GovernancePanel from './GovernancePanel.vue'
import Office3DCanvas from './Office3DCanvas.vue'
import OfficeHoverCard from './OfficeHoverCard.vue'
import EmployeeManager from './EmployeeManager.vue'
import TaskBoard from './TaskBoard.vue'
import AssistantFloatingButton from '@/components/assistant/AssistantFloatingButton.vue'
import AssistantPanel from '@/components/assistant/AssistantPanel.vue'
import { usePetModelStore } from '@/store/petModel'

defineOptions({ name: 'AiOfficeView' })

const teamMeta = ref<{ name?: string; description?: string; color?: string }>({})
// 全量清单 vs 档案过滤后的视图清单（v4 第 2 步）：展示面（3D/房间/选择器/管理面清单）按当前
// 办公室过滤；编辑面（TeamManager 批量回存房间）拿全量，防按过滤清单回存把隐藏房间删掉。
const colleaguesAll = ref<any[]>([])
const roomsAll = ref<any[]>([])
const colleagues = computed(() =>
  colleaguesAll.value.filter((c) => inOffice('role', String(c?.role_key || ''))))
const viewRooms = computed(() =>
  roomsAll.value.filter((r) => inOffice('room', String(r?.id || ''))))
const rooms = roomsAll
const activeRoomId = ref('default')
const layoutNodes = ref<any[]>([])
const layoutEdges = ref<any[]>([])
const officeConfig = ref<OfficeConfig>({})
const teamGraph = ref<{ lead_role_key?: string; subagent_role_keys?: string[] }>({})
const behaviorConfig = ref<BehaviorConfig>({})
const manageOpen = ref(false)
// 档案直达：非空 = Manage Teams 打开后直达该同事的档案编辑弹层
const archiveRoleKey = ref<string | null>(null)
const governanceOpen = ref(false)
const selectedRoleKey = ref<string | null>(null)
const missions = ref<OfficeMission[]>([])
const missionPanelOpen = ref(false)
const missionLoading = ref(false)
const missionError = ref('')
let missionPollTimer: ReturnType<typeof setInterval> | null = null

const auth = useAuthStore()
const petModel = usePetModelStore()
const assistantOpen = ref(false)
// 办公室档案：工作区自愈对齐 cpq 档案（工作区=cpq 应用的工作区；档案切换=回桌面，见桌面磁贴模型）
const { currentKey, setOffices, switchOffice, inOffice } = useOfficeProfile()
const canManageOffice = computed(() => auth.can('ai.office.manage'))
// 管理面任一段可见即可打开（只授 ai.office.admin 的账号也要能进「模型与接入/运行与权限」）
const canOpenOfficeManagement = computed(() => auth.can('ai.office.manage') || auth.can('ai.office.admin'))

// ── 同事名片浮层（悬停卡/名册/房间均可唤起）──

const { statusMap, connected, connect, disconnect } = useOfficeSocket()

const emptyStatus: OfficeColleagueStatus = {
  type: 'colleague_status',
  role_key: '',
  status: 'idle',
  activity: '',
  message: '',
}

const activeRoom = computed(() => viewRooms.value.find((room) => room.id === activeRoomId.value) || viewRooms.value[0] || null)
const roomColleagues = computed(() => {
  const roleKeys = activeRoom.value?.role_keys || []
  if (!roleKeys.length) return colleagues.value
  const allowed = new Set(roleKeys)
  return colleagues.value.filter((colleague) => allowed.has(colleague.role_key))
})

watch(
  roomColleagues,
  (list) => {
    if (list.length && !list.find((c) => c.role_key === selectedRoleKey.value)) {
      selectedRoleKey.value = list[0].role_key
    }
  },
  { immediate: true },
)

// ── 手机端（≤860）：3D 全屏 + 底部同事头像行 + 任务左抽屉 + 全屏聊天层 ──
const isMobile = ref(false)
let _mqListener: ((e: MediaQueryListEvent) => void) | null = null
const tasksOpen = ref(false)
/* 管理面三个全屏层任一打开时给 body 挂标记（z900 全屏层会被悬浮横幅 z2100 / AI 悬浮球 z1550 压住），
   悬浮件据此让位——与同事档案弹层的 em-editor-modal-open 同一机制 */
watch([manageOpen, governanceOpen, tasksOpen], ([m, g, t]) => {
  document.body.classList.toggle('office-fullscreen-open', m || g || t)
})
// 点 3D 显示器带入的任务板聚焦：{ missionId }=直开详情；{ roleKey }=按同事名过滤
const missionFocus = ref<{ missionId?: string; roleKey?: string } | null>(null)
const runningMissionCount = computed(
  () => missions.value.filter((m) => m.status === 'running' || m.status === 'queued').length,
)
// 3D 点同事与头像行殊途同归：同一 selectedRoleKey，进统一聊天窗（全端一套）
function onMobileMoreMenu({ key }: { key: string | number }) {
  if (key === 'tasks') tasksOpen.value = true
  else if (key === 'gov') governanceOpen.value = true
}
// 返回桌面（应用启动台）
const router = useRouter()
function goDesktop() { router.push('/') }
function avatarDotColor(c: any) {
  return behaviorStatusMeta(statusFor(c.role_key).status).color || '#9aa4b2'
}
onMounted(() => {
  isMobile.value = window.matchMedia('(max-width: 860px)').matches
  const mq = window.matchMedia('(max-width: 860px)')
  _mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', _mqListener)
  // 名册钉住的悬停卡：点卡外任意处关闭
  document.addEventListener('click', onDocClickClose)
})
onBeforeUnmount(() => {
  if (_mqListener) window.matchMedia('(max-width: 860px)').removeEventListener('change', _mqListener)
  document.removeEventListener('click', onDocClickClose)
})

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

function selectColleague(roleKey: string, x?: number, y?: number) {
  selectedRoleKey.value = roleKey
  // 桌面：3D 点同事 = 钉出 [档案][聊天] 卡（悬停不再显示）；手机 = 直接开统一聊天窗
  if (isMobile.value) {
    openChat(roleKey)
  } else {
    hoverCard.value = { roleKey, x: x || window.innerWidth / 2, y: y || window.innerHeight / 2, pinned: true }
  }
}

// ── 同事卡（对齐 workstation-teacher hcard 契约）：点击才出现（3D 点同事/右栏名册），
//    钉住显示；点卡外关闭；[聊天][档案] 双动作。悬停不显示。──
const hoverCard = ref<{ roleKey: string; x: number; y: number; pinned?: boolean } | null>(null)
const hoverColleague = computed(() =>
  hoverCard.value ? colleagues.value.find((c) => c.role_key === hoverCard.value!.roleKey) || null : null)
const hoverStatus = computed(() =>
  hoverCard.value ? statusFor(hoverCard.value.roleKey) : emptyStatus)
const hoverColor = computed(() =>
  hoverColleague.value ? deskColor(hoverColleague.value) : 'var(--cpq-accent-primary)')
const hoverStats = computed(() => {
  const list = missions.value.filter((m) => m.owner_role_key === hoverCard.value?.roleKey)
  return {
    active: list.filter((m) => m.status === 'running' || m.status === 'queued').length,
    done: list.filter((m) => m.status === 'done' || m.status === 'completed').length,
    total: list.length,
  }
})

// 名册点同事 = 同一张卡（钉住，点卡外关闭），不直接开聊天窗
function showRailCard(colleague: any, ev: MouseEvent) {
  hoverCard.value = { roleKey: colleague.role_key, x: ev.clientX, y: ev.clientY, pinned: true }
}
function onDocClickClose(e: MouseEvent) {
  if (!hoverCard.value) return
  const t = e.target as HTMLElement
  // canvas 的点击由 select/deselect 事件裁决（click 冒泡晚于 pointerup 开卡，不能当"点外"）
  if (t.closest('.ohc') || t.closest('.rail-item') || t.closest('canvas')) return
  hoverCard.value = null
}
function closeRoleCard() { hoverCard.value = null }
function hoverChat() {
  const c = hoverColleague.value
  hoverCard.value = null
  if (c) openChat(c.role_key)
}
function hoverArchive() {
  const c = hoverColleague.value
  hoverCard.value = null
  if (c) openArchive(c.role_key)
}
// 档案 = 该同事的完整档案编辑页（独立挂载的「同事档案」弹窗，定位到人；不经过 Manage Teams 全屏壳）
function openArchive(roleKey: string) {
  selectedRoleKey.value = roleKey
  archiveRoleKey.value = roleKey
}

// ── 统一聊天窗 = 浮动 AI 角色的消息中心面板（AssistantPanel，全端一套；切换=回桌面）──
const assistantPanelRef = ref<InstanceType<typeof AssistantPanel> | null>(null)
function openChat(target: string) {
  assistantOpen.value = true
  if (target === 'room') {
    assistantPanelRef.value?.openGroup()
  } else {
    assistantPanelRef.value?.openDm({ role_key: target })
  }
}

// ── 右栏「今日」：状态分布（同事 × 实时状态）──
const workingCount = computed(() =>
  roomColleagues.value.filter((c) => statusFor(c.role_key).status === 'working').length)
const railStatusSegs = computed(() => {
  const counts: Record<string, number> = {}
  for (const c of roomColleagues.value) {
    const s = statusFor(c.role_key).status || 'idle'
    counts[s] = (counts[s] || 0) + 1
  }
  return Object.entries(counts)
    .map(([status, count]) => ({ status, count, label: statusText(status), color: behaviorStatusMeta(status).color || '#9aa4b2' }))
    .sort((a, b) => b.count - a.count)
})

function formatEventTime(ts?: number): string {
  if (!ts) return '--:--:--'
  return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
}

async function loadConfig() {
  try {
    const data = await officeApi.teamConfig()
    teamMeta.value = data.team_meta || {}
    colleaguesAll.value = Array.isArray(data.colleagues) ? data.colleagues : []
    roomsAll.value = Array.isArray(data.rooms) ? data.rooms : []
    setOffices(data.offices)
    // 工作区自愈：无论 localStorage 记的什么档案，工作区永远对齐 cpq（切换=回桌面）
    if (currentKey.value !== 'cpq') switchOffice('cpq')
    if (viewRooms.value.length && !viewRooms.value.some((room) => room.id === activeRoomId.value)) {
      activeRoomId.value = viewRooms.value[0].id
    }
    layoutNodes.value = Array.isArray(data.layout?.nodes) ? data.layout.nodes : []
    layoutEdges.value = Array.isArray(data.layout?.edges) ? data.layout.edges : []
    officeConfig.value = normalizeOfficeConfig(data.layout?.office || {})
    teamGraph.value = data.layout?.team_graph || {}
    behaviorConfig.value = data.behavior || {}
  } catch (error: any) {
    colleaguesAll.value = []
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
  missionFocus.value = null
  missionPanelOpen.value = true
}

// 点 3D 显示器 → 任务板聚焦该同事：运行中任务直开详情 → 名下最新任务按名过滤 → 手头没任务只提示不开板
function onOpenMission(roleKey: string) {
  const runningId = statusFor(roleKey).mission_id
  if (runningId && missions.value.some((m) => m.mission_id === runningId)) {
    missionFocus.value = { missionId: runningId }
  } else {
    const mine = [...missions.value].reverse().find(
      (m) => m.owner_role_key === roleKey || (m.steps || []).some((s) => s.role_key === roleKey),
    )
    if (!mine) {
      message.info(`${colleagueName(roleKey)} 手头暂无任务`)
      return
    }
    missionFocus.value = { roleKey }
  }
  if (isMobile.value) tasksOpen.value = true
  else missionPanelOpen.value = true
}

function closeTasksBoard() {
  missionPanelOpen.value = false
  tasksOpen.value = false
  missionFocus.value = null
}

async function onTeamSaved() {
  await loadConfig()
}

onMounted(() => {
  connect()
  loadConfig()
  loadMissions()
  startMissionPolling()
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
/* 满高工作台直接躺在共享画布上：无外层托盘包裹，三栏间 hairline 分隔
   （3D 场景自带衬底；工具栏/列表面板透明，画布透出与全站同语言） */
.ai-office-shell {
  position: relative;
  height: calc(100% - var(--cpq-header-clearance, 0px));
  /* 手机端让位全局底栏（桌面 inset=0 无效） */
  padding-bottom: var(--cpq-tabbar-inset, 0px);
  min-height: 0;
  display: flex;
  flex-direction: column;
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
  border-radius: var(--cpq-radius-full);
  font-size: var(--cpq-font-size-xs);
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

/* 三栏工作区（无顶栏）：左=任务看板（回桌面）｜中=3D 办公区满高｜右=办公室状态栏 */
.office-workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr) 312px;
  overflow: hidden;
}


/* 左栏：任务看板平铺全高（无玻璃罩框） */
.office-sidebar {
  min-height: 0;
  overflow-y: auto;
  padding: var(--cpq-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-3);
  border-right: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

/* 看板头（标题行 + 打开看板） */
.board-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--cpq-space-2);
}
.board-head-text { min-width: 0; }
.board-title { font-size: var(--cpq-font-size-base); font-weight: 700; color: var(--cpq-text-primary); }
.board-desc { margin-top: 2px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }

/* 顶部回桌面（桌面左栏=全宽行；移动顶栏=紧凑图标） */
.ws-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--cpq-space-2);
  height: 34px;
  padding: 0 var(--cpq-space-3);
  border-radius: var(--cpq-radius-md);
  color: var(--cpq-text-secondary);
  background: var(--cpq-glass-2-bg);
  border: 1px solid var(--cpq-glass-border);
  font-size: var(--cpq-font-size-sm);
  font-weight: 600;
  transition: all var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.ws-back:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.office-sidebar .ws-back { width: 100%; justify-content: flex-start; }

.office-sidebar::-webkit-scrollbar {
  width: 8px;
}

.office-sidebar::-webkit-scrollbar-thumb {
  border-radius: var(--cpq-radius-full);
  background: var(--cpq-overlay-w10, rgba(255,255,255,0.12));
}

.office-sidebar::-webkit-scrollbar-thumb:hover {
  background: var(--cpq-overlay-w15, rgba(255,255,255,0.18));
}

/* 画布上面板卡 = 系统标准玻璃卡（与策略中心模块卡同配方） */
.sidebar-section {
  padding: 14px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
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
  font-size: var(--cpq-font-size-xs);
  line-height: 1.35;
  color: var(--cpq-text-muted);
}

.sidebar-empty {
  padding: 16px 10px;
  border-radius: var(--cpq-radius-md);
  font-size: var(--cpq-font-size-sm);
  color: var(--cpq-text-muted);
  text-align: center;
  background: var(--cpq-overlay-w4, rgba(255,255,255,0.04));
}

.sidebar-mission-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 10px;
  border-radius: var(--cpq-radius-md);
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
  font-size: var(--cpq-font-size-sm);
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
  border: 1px solid var(--cpq-border-secondary);
  border-radius: var(--cpq-radius-sm);
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w4);
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
  border-radius: var(--cpq-radius-md);
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
  border-radius: var(--cpq-radius-md);
  box-shadow: inset 0 0 0 1px var(--cpq-overlay-w8);
}

.sidebar-colleague-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar-colleague-name {
  font-size: var(--cpq-font-size-sm);
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
  border-radius: var(--cpq-radius-full);
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
}

/* 画布浮动件：标题 + 图例悬在画布上沿（中栏拉到顶后不再占一行） */
.map-float {
  position: absolute;
  top: var(--cpq-space-3);
  left: var(--cpq-space-4);
  right: var(--cpq-space-4);
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--cpq-space-3);
  padding: var(--cpq-space-2) var(--cpq-space-3);
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-glass-3-bg, rgba(18, 24, 38, 0.75));
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-glass-border);
  font-size: var(--cpq-font-size-sm);
  color: var(--cpq-text-secondary);
  pointer-events: none;
}
.map-float .map-title,
.map-float .map-legend { pointer-events: auto; }

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
  font-size: var(--cpq-font-size-xs);
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
  font-size: var(--cpq-font-size-xs);
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
  border-radius: var(--cpq-radius-full);
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
  border-radius: var(--cpq-radius-xl);
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
  border-radius: var(--cpq-radius-full);
  font-size: var(--cpq-font-size-xs);
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

/* ── 右栏：办公室状态栏（命令+今日+名册+房间+动态；平铺分区+发丝线） ── */
.office-rail {
  min-height: 0;
  overflow-y: auto;
  padding: var(--cpq-space-4);
  border-left: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-4);
}

.rail-cmds {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2);
  flex-wrap: wrap;
}
.rail-cmds .connection-pill { margin-right: auto; }

.rail-sec {
  padding-bottom: var(--cpq-space-4);
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}
.rail-sec:last-child { border-bottom: 0; padding-bottom: 0; }

.rail-k {
  font-size: var(--cpq-font-size-sm);
  font-weight: 700;
  color: var(--cpq-text-secondary);
  margin-bottom: var(--cpq-space-2);
}
.rail-n { color: var(--cpq-text-muted); font-weight: 500; }

.rail-big {
  font-size: var(--cpq-font-size-2xl);
  font-weight: 700;
  color: var(--cpq-text-primary);
  font-variant-numeric: tabular lining;
  line-height: 1.1;
}
.rail-big small { font-size: var(--cpq-font-size-xs); font-weight: 500; color: var(--cpq-text-muted); margin-left: 4px; }

.rail-bar {
  display: flex;
  height: 6px;
  border-radius: var(--cpq-radius-full);
  overflow: hidden;
  gap: 2px;
  margin: var(--cpq-space-2) 0 var(--cpq-space-1);
  background: var(--cpq-overlay-w4, rgba(255,255,255,0.04));
}
.rail-bar i { display: block; min-width: 3px; }
.rail-bar-legend { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.rail-bar-legend span { display: inline-flex; align-items: center; gap: 4px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.rail-bar-legend i { width: 6px; height: 6px; border-radius: 50%; }

.rail-list { display: flex; flex-direction: column; gap: 2px; }
.rail-item {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2);
  padding: 6px 8px;
  border-radius: var(--cpq-radius-md);
  border: 1px solid transparent;
  background: none;
  color: inherit;
  text-align: left;
  width: 100%;
  cursor: pointer;
  transition: background var(--cpq-dur-1) var(--cpq-ease-out-expo), border-color var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.rail-item:hover { background: var(--cpq-overlay-w4, rgba(255,255,255,0.04)); border-color: var(--cpq-border-secondary, rgba(255,255,255,0.06)); }
.rail-item.is-active { border-color: var(--cpq-glass-border-strong, rgba(22,119,255,.4)); background: var(--cpq-overlay-w4, rgba(255,255,255,0.04)); }
.rail-item-av {
  width: 30px; height: 30px; flex: none; border-radius: 50%;
  display: grid; place-items: center; overflow: hidden;
  color: var(--cpq-accent-on-primary); font-size: var(--cpq-font-size-sm); font-weight: 700;
}
.rail-item-av img { width: 100%; height: 100%; object-fit: cover; }
.rail-item-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 1px; }
.rail-item-main b { font-size: var(--cpq-font-size-sm); font-weight: 600; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rail-item-main small { display: inline-flex; align-items: center; gap: 4px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.rail-item-main small i { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.rail-cur { font-size: var(--cpq-font-size-xs); color: var(--cpq-accent-primary); flex: none; }
.rail-chat {
  flex: none;
  height: 24px; padding: 0 10px;
  border-radius: var(--cpq-radius-full);
  border: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-2-bg);
  color: var(--cpq-text-secondary);
  font-size: var(--cpq-font-size-xs);
  transition: all var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.rail-chat:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.rail-chat--block { width: 100%; height: 30px; margin-top: var(--cpq-space-2); }

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
  border-radius: var(--cpq-radius-xl);
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

/* ============ 手机端（≤860）：3D 全屏 + 头像行 + 聊天层 + 任务抽屉 ============ */
.of-more {
  position: relative;
  width: 32px;
  height: 32px;
  border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
  color: var(--cpq-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  cursor: pointer;
}

/* 更多按钮红点：有运行中任务时提示去菜单里开任务看板（原任务按钮徽标的轻量替身） */
.of-more-dot {
  position: absolute;
  top: -3px;
  right: -3px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--cpq-accent-warning, #faad14);
}

.m-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
  /* 让出左侧同事竖栏宽度 */
  margin-left: 62px;
}

.m-legend {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 7px 10px;
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-glass-3-bg, var(--cpq-overlay-w5));
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

.m-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 9.5px;
  color: var(--cpq-text-secondary);
}

.m-legend i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.m-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 32px;
  text-align: center;
  font-size: 12.5px;
  color: var(--cpq-text-muted);
}

.m-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
}

/* 左侧同事竖栏：复用原头像行容器，CSS 重定位到左缘竖排（改模板包裹层会触发 vue-tsc 推断塌陷，故不动模板） */
.m-peoplebar {
  position: absolute;
  left: 0;
  top: 60px;
  bottom: var(--cpq-tabbar-inset, 0px);
  width: 62px;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 5px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
  background: var(--cpq-glass-3-bg, var(--cpq-overlay-w5));
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  backdrop-filter: blur(16px) saturate(1.3);
  border-right: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

.m-peoplebar::-webkit-scrollbar { display: none; }

.m-people-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.m-pav {
  position: relative;
  flex: none;
  width: 42px;
  border: none;
  background: transparent;
  padding: 0;
  text-align: center;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.m-pav .m-av {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  overflow: hidden;
  border: 2px solid transparent;
  box-shadow: 0 4px 10px var(--cpq-shadow-color, rgba(31, 42, 61, 0.18));
}

.m-pav .m-av img { width: 100%; height: 100%; object-fit: cover; }

.m-pav.is-active .m-av { border-color: var(--cpq-accent-primary); }

.m-pav .m-nm {
  display: block;
  font-size: 8.5px;
  color: var(--cpq-text-secondary);
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-pav .m-st {
  position: absolute;
  top: 28px;
  right: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--cpq-glass-card-bg, #fff);
}

.m-people-empty { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }

/* 聊天窗全端统一为消息中心面板（AssistantPanel 浮层） */

.m-chatup-enter-active,
.m-chatup-leave-active { transition: transform 0.3s var(--cpq-ease-smooth, ease), opacity 0.3s var(--cpq-ease-smooth, ease); }

.m-chatup-enter-from,
.m-chatup-leave-to { transform: translateY(100%); opacity: 0.6; }

/* 任务全屏层：TaskBoard 甘特/清单 min-width 960 → 双向滚动；头部折行防炸 */
.m-tasklayer {
  position: absolute;
  inset: 0;
  z-index: 50;
  background: var(--cpq-bg-primary);
}

.m-taskscroll {
  position: absolute;
  inset: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

.m-taskscroll :deep(.tc-root) {
  height: auto;
  min-height: 100%;
  overflow: visible;
}

.m-taskscroll :deep(.tc-header) {
  flex-wrap: wrap;
  gap: 8px 12px;
}

.m-taskscroll :deep(.tc-heading) {
  flex: 1 1 100%;
}

.m-taskscroll :deep(.tc-actions) {
  flex: 1 1 100%;
  flex-wrap: wrap;
}

.m-taskscroll :deep(.tc-search) {
  flex: 1 1 160px;
  min-width: 0;
  max-width: none;
}

.m-taskscroll :deep(.tc-nav) {
  flex-wrap: wrap;
}

@media (max-width: 860px) {
  .office-toolbar { padding: 0 12px; gap: 8px; }

  /* 顶栏元素（回桌面/LIVE/Manage Teams/更多）在 360px 级窄屏放不下，"更多"会被挤出屏——
     LIVE 只留状态圆点（颜色即在线/离线语义），Manage Teams 收紧内边距 */
  .connection-pill { padding: 0 7px; }
  .connection-pill-text { display: none; }
  .office-actions { gap: 8px; }
  .office-actions :deep(.ant-btn) { padding: 0 8px; font-size: var(--cpq-font-size-sm); }

  .manager-backdrop { padding: 0; }

  .manager-shell { border-radius: 0; border: none; }
}
</style>
