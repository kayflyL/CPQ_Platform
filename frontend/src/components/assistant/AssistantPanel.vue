<template>
  <Teleport to="body">
    <transition name="assistant-panel">
      <div v-if="open" class="assistant-panel" :style="panelStyle">
        <!-- header（可拖动）-->
        <div class="ap-header" @mousedown="startDrag">
          <div class="ap-title">
            <RobotOutlined />
            <span>方案助手</span>
          </div>
          <div class="ap-ctx" v-if="contextLabel">
            <span class="ap-ctx-dot"></span>{{ contextLabel }}
          </div>
          <div class="ap-ctx ap-ctx-none" v-else>无上下文</div>
          <button class="ap-close" @click="emit('update:open', false)" title="收起">
            <CloseOutlined />
          </button>
        </div>

        <!-- thread 切换 -->
        <div class="ap-threads">
          <a-select
            :value="currentThreadId || undefined"
            size="small"
            class="ap-thread-select"
            :placeholder="threads.length ? `切换会话（共 ${threads.length} 个）` : '还没有会话'"
            :options="threadOptions"
            :allow-clear="false"
            :get-popup-container="getPopupContainer"
            @change="(id: any) => selectThread(String(id))"
          >
            <template #option="{ value, label }">
              <div class="thread-opt">
                <span class="thread-opt-label">{{ label }}</span>
                <DeleteOutlined class="thread-opt-del" @click.stop="onDeleteThread(String(value))" />
              </div>
            </template>
          </a-select>
          <a-button size="small" @click="onNewThread" :loading="loading">
            <template #icon><PlusOutlined /></template>
            新会话
          </a-button>
        </div>

        <!-- 消息列表 -->
        <div class="ap-messages" ref="messagesEl">
          <a-spin v-if="loading" size="small" class="ap-spin" />
          <a-empty
            v-else-if="!messages.length && !streamingText && !waitingAI && !analysisSteps.length && !analysisPlans.length && !analysisRunning && !analysisPrompt && !analysisConfirm && !analysisError"
            :image-style="{ height: '48px' }"
            description="和方案助手聊聊？输入消息开始，或点下方「需求分析 / 生成 BOM」"
          />
          <div v-else class="ap-msg-list">
            <div
              v-for="m in messages"
              :key="m.message_id"
              class="ap-msg"
              :class="`role-${m.role}`"
            >
              <div class="ap-bubble">{{ m.content }}</div>
            </div>
            <!-- 需求分析：步骤时间线（运行中）-->
            <div v-if="analysisSteps.length" class="ap-steps">
              <span
                v-for="s in analysisSteps"
                :key="s.key"
                class="ap-step"
                :class="`st-${s.status}`"
              >
                {{ s.label }}
              </span>
            </div>
            <!-- 需求分析：整机方案卡（BOM）-->
            <template v-if="analysisPlans.length">
              <p class="ap-note">以下为整机方案（可查看 BOM 明细）：</p>
              <PlanCard
                v-for="p in analysisPlans"
                :key="p.config_id"
                :plan="p"
                class="ap-plan-card"
                @view-bom="viewDetail(p)"
              >
                <template #extra-actions>
                  <a-button
                    v-if="currentThread?.opportunity_id"
                    type="primary"
                    size="small"
                    :loading="convertingId === p.config_id"
                    @click="convertPlan(p)"
                  >
                    <template #icon><ArrowRightOutlined /></template>
                    转为报价单
                  </a-button>
                </template>
              </PlanCard>
            </template>
            <!-- 需求分析失败 -->
            <p v-if="analysisError" class="ap-bubble err"><ExclamationCircleOutlined /> {{ analysisError }}</p>
            <div v-if="streamingText || waitingAI" class="ap-msg role-assistant">
              <div class="ap-bubble">
                <template v-if="streamingText">{{ streamingText }}<span class="ap-cursor">▍</span></template>
                <span v-else class="ap-typing"><i></i><i></i><i></i></span>
              </div>
            </div>
            <div v-if="analysisRunning" class="ap-msg role-assistant">
              <div class="ap-bubble"><span class="ap-typing"><i></i><i></i><i></i></span></div>
            </div>
          </div>
        </div>

        <!-- 快捷指令：需求分析（常驻）+ 按当前页 provider 条件渲染 -->
        <div class="ap-quick">
          <button
            class="ap-quick-chip primary"
            :class="{ active: analyzeMode }"
            :disabled="analysisBusy"
            @click="toggleAnalyzeMode"
          >
            <span class="ap-quick-icon">🧩</span>
            <span>{{ analyzeMode ? '退出需求分析' : '需求分析 / 生成 BOM' }}</span>
          </button>
          <button
            v-for="a in visibleQuickActions"
            :key="a.key"
            class="ap-quick-chip"
            :disabled="sending"
            @click="onQuickAction(a)"
          >
            <span v-if="a.icon" class="ap-quick-icon">{{ a.icon }}</span>
            <span>{{ a.label }}</span>
          </button>
        </div>

        <!-- 需求分析：反问回复区（ask_user 节点触发，pipeline 暂停等用户补齐）-->
        <div v-if="analysisPrompt" class="ap-reply-footer">
          <p class="ap-reply-q">{{ analysisPrompt.question }}</p>
          <p v-if="analysisPrompt.format" class="ap-note ap-format">{{ analysisPrompt.format }}</p>
          <div v-if="analysisPrompt.options?.length" class="ap-reply-options">
            <a-tag
              v-for="opt in analysisPrompt.options"
              :key="opt"
              class="ap-reply-opt"
              @click="quickReply(opt)"
            >{{ opt }}</a-tag>
          </div>
          <a-textarea
            v-model:value="replyText"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            :placeholder="analysisPrompt.clarity_capped ? '已多次补充，可直接发送或跳过' : '回复补充信息，回车发送（Shift+Enter 换行）'"
            class="ap-reply-input"
            @press-enter="onReplyEnter"
          />
          <div class="ap-reply-actions">
            <a-button size="small" @click="onSkipAnalysis">跳过</a-button>
            <a-button type="primary" size="small" :disabled="!replyText.trim()" @click="submitReply">
              <template #icon><ArrowRightOutlined /></template>
              发送
            </a-button>
          </div>
        </div>

        <!-- 需求分析：LLM 确认面板（confirm 节点，默认采纳、高亮可改）-->
        <div v-if="analysisConfirm" class="ap-confirm-footer">
          <p class="ap-confirm-title"><BulbOutlined /> {{ analysisConfirm.question }}</p>
          <div
            v-for="it in analysisConfirm.items"
            :key="it.id"
            class="ap-confirm-item"
            :class="{ accepted: (confirmChoices[it.id] || analysisConfirm.default || 'accept') === 'accept' }"
          >
            <div class="ap-confirm-info">
              <span class="ap-confirm-label">{{ it.label }}</span>
              <a-tag v-if="it.level === 'conflict'" color="orange" class="ap-confirm-tag">与规则冲突</a-tag>
              <a-tag v-else color="blue" class="ap-confirm-tag">低置信度</a-tag>
              <span v-if="it.rule != null" class="ap-confirm-v">规则：{{ it.rule }}</span>
              <span class="ap-confirm-v llm">LLM：{{ it.llm || '—' }}</span>
              <span v-if="it.confidence != null" class="ap-confirm-conf">置信 {{ Math.round(it.confidence * 100) }}%</span>
            </div>
            <div class="ap-confirm-opts">
              <a-button size="small" :type="(confirmChoices[it.id] || 'accept') === 'accept' ? 'primary' : 'default'" @click="setConfirmChoice(it.id, 'accept')">采纳</a-button>
              <a-button size="small" :type="(confirmChoices[it.id] || 'accept') === 'ignore' ? 'danger' : 'default'" @click="setConfirmChoice(it.id, 'ignore')">忽略</a-button>
            </div>
          </div>
          <div class="ap-confirm-actions">
            <a-button size="small" @click="onAcceptAll">全部采纳，查看方案</a-button>
            <a-button type="primary" size="small" :disabled="!hasConfirmIgnore" @click="onConfirmSubmit">按以上选择重新生成</a-button>
          </div>
          <p class="ap-note" style="margin-top:6px">「全部采纳」直接看当前方案（不重跑 LLM）；改了选择才重新生成。</p>
        </div>

        <!-- 输入（需求分析模式 = 在会话里直接发需求）-->
        <div class="ap-analyze-bar" v-if="analyzeMode">
          <span class="ap-analyze-bar-tip">🧩 需求分析模式：把客户需求直接发出来，Enter 开始；再点上方「退出需求分析」返回聊天。</span>
        </div>
        <div class="ap-input">
          <a-textarea
            v-model:value="draft"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            :placeholder="analyzeMode ? '输入客户需求，Enter 开始需求分析（Shift+Enter 换行）' : '输入消息，Enter 发送 / Shift+Enter 换行'"
            :disabled="sending"
            @press-enter="onEnter"
          />
          <a-button type="primary" :loading="analysisBusy || sending" :disabled="!draft.trim()" @click="onSend">
            <template #icon v-if="analyzeMode"><ThunderboltOutlined /></template>
            {{ analyzeMode ? '开始分析' : '发送' }}
          </a-button>
        </div>
      </div>
    </transition>

          <!-- BOM 详情抽屉（复用工作台 BomTable，与商机详情页推理面板一致）-->
      <a-drawer
        v-model:open="drawerOpen"
        :title="drawerPlan?.name || '整机 BOM 详情'"
        placement="right"
        width="560"
        class="ap-bom-drawer"
      >
        <div class="ap-bom-wrap" v-if="drawerPlan">
          <div class="ap-bom-summary">
            {{ [drawerPlan.series, drawerPlan.form, drawerPlan.bays != null ? `${drawerPlan.bays}盘位` : ''].filter(Boolean).join(' · ') }}
            · 底盘 {{ drawerPlan.summary.parts_count }} 件 + KP {{ drawerPlan.summary.kp_count }} 件
          </div>
          <a-spin :spinning="drawerLoading" tip="转 BOM 模板格式…">
            <BomTable v-if="drawerCfg" :cfg="drawerCfg" />
          </a-spin>
        </div>
      </a-drawer>

  </Teleport>
</template>


<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import {
  RobotOutlined, PlusOutlined, CloseOutlined, DeleteOutlined,
  ArrowRightOutlined, BulbOutlined, ExclamationCircleOutlined, ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { Modal, message as antMessage } from 'ant-design-vue'
import { useAssistant } from '@/composables/useAssistant'
import { useAssistantContext, type QuickAction } from '@/composables/assistantContext'
import { useAssistantFab, computePanelAnchor } from '@/composables/useAssistantFab'
import PlanCard from '@/components/reasoning/PlanCard.vue'
import BomTable from '@/components/BomTable.vue'
import { buildPlanCfg, type PlanLiveCfg } from '@/composables/usePlanBom'
import { quotationApi } from '@/api'
import type { Plan } from '@/api/reasoning'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const {
  threads, currentThreadId, currentThread, messages, loading, sending, streamingText, waitingAI,
  loadThreads, selectThread, newThread, send, removeThread, connectWs, disconnectWs,
  analysisSteps, analysisPlans, analysisRunning, analysisBusy, analysisError,
  analysisPrompt, analysisConfirm,
  runAnalysis, replyAnalysis, skipAnalysis, confirmAnalysis, acceptAllAnalysis,
} = useAssistant()

const { contextLabel, summarize, visibleQuickActions } = useAssistantContext()

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)

// 面板贴着 FAB 当前位置打开（FAB 拖到哪儿，面板就跟到哪儿附近）
const { pos: fabPos, getFabRect } = useAssistantFab()
const viewportTick = ref(0)

// 用户拖动后的偏移量（持久化到 sessionStorage）
const dragOffset = ref({ x: 0, y: 0 })
const DRAG_KEY = 'assistant-panel-offset'

// 加载已保存的偏移
onMounted(() => {
  try {
    const saved = sessionStorage.getItem(DRAG_KEY)
    if (saved) {
      dragOffset.value = JSON.parse(saved)
    }
  } catch {
    /* ignore */
  }
})

const panelStyle = computed(() => {
  // 依赖 fabPos / viewportTick 触发重算（FAB 拖动或窗口缩放时跟着挪）
  void fabPos.value
  void viewportTick.value
  const rect = getFabRect()
  if (!rect) return undefined // FAB 还没挂载 → 回落 CSS 默认（右下角）
  const vw = window.innerWidth
  const vh = window.innerHeight
  const { left, top, height } = computePanelAnchor(rect, vw, vh)
  // 应用用户拖动偏移
  return {
    left: left + dragOffset.value.x + 'px',
    top: top + dragOffset.value.y + 'px',
    right: 'auto',
    bottom: 'auto',
    height: height + 'px',
    maxHeight: height + 'px',
  }
})
function onResize() { viewportTick.value++ }
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

// 拖动逻辑
let dragging = false
let dragStart = { x: 0, y: 0 }
let offsetStart = { x: 0, y: 0 }

function startDrag(e: MouseEvent) {
  // 忽略关闭按钮点击
  if ((e.target as HTMLElement).closest('.ap-close')) return

  dragging = true
  dragStart = { x: e.clientX, y: e.clientY }
  offsetStart = { ...dragOffset.value }

  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)

  // 防止选中文字
  e.preventDefault()
}

function onDrag(e: MouseEvent) {
  if (!dragging) return

  const dx = e.clientX - dragStart.x
  const dy = e.clientY - dragStart.y

  dragOffset.value = {
    x: offsetStart.x + dx,
    y: offsetStart.y + dy,
  }
}

function stopDrag() {
  if (!dragging) return
  dragging = false

  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)

  // 持久化偏移
  try {
    sessionStorage.setItem(DRAG_KEY, JSON.stringify(dragOffset.value))
  } catch {
    /* ignore */
  }
}

// vue-tsc 模板里拿不到全局 document，集中到 script setup 暴露
const getPopupContainer = (node: any) => node?.closest('.assistant-panel') || document.body

const threadOptions = computed(() =>
  threads.value.map((t) => ({ value: t.thread_id, label: t.title || '新会话' })),
)

watch(
  () => props.open,
  async (v) => {
    if (v) {
      await loadThreads()
      if (currentThreadId.value) connectWs(currentThreadId.value)
    } else {
      disconnectWs()
    }
  },
  { immediate: true },
)

watch(() => messages.value.length, async () => {
  await nextTick(scrollToBottom)
})
watch(streamingText, async () => {
  await nextTick(scrollToBottom)
})

function scrollToBottom() {
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

function onEnter(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  onSend()
}

async function onSend() {
  const text = draft.value
  if (!text.trim() || sending.value) return
  draft.value = ''
  if (analyzeMode.value) {
    analyzeMode.value = false
    await runAnalysis(text)
    return
  }
  const summary = await summarize()
  await send(text, summary)
}

// 快捷指令：prompt 可为函数（动态读配置，如趋势分析）；context 缺省走通用 provider 摘要
async function onQuickAction(action: QuickAction) {
  if (sending.value) return
  const prompt = typeof action.prompt === 'function' ? await action.prompt() : action.prompt
  const ctx = action.context ? await action.context() : await summarize()
  await send(prompt, ctx)
}

// ── 需求分析：会话内模式（点「需求分析」切换输入框，直接发需求，不再弹窗）──
const analyzeMode = ref(false)
const router = useRouter()

function toggleAnalyzeMode() {
  analyzeMode.value = !analyzeMode.value
  if (analyzeMode.value) {
    nextTick(() => {
      const ta = document.querySelector('.assistant-panel .ap-input textarea') as HTMLTextAreaElement | null
      ta?.focus()
    })
  }
}

// ── 需求分析：反问回复（ask_user）──
const replyText = ref('')
const quickLocked = ref(false)
function quickReply(opt: string) {
  if (quickLocked.value) return
  quickLocked.value = true
  replyText.value = ''
  replyAnalysis(opt)
}
function submitReply() {
  const t = replyText.value.trim()
  if (!t) return
  replyText.value = ''
  replyAnalysis(t)
}
function onReplyEnter(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  submitReply()
}
function onSkipAnalysis() {
  replyText.value = ''
  skipAnalysis()
}
watch(() => analysisPrompt.value, () => {
  quickLocked.value = false
  nextTick(scrollToBottom)
})

// ── 需求分析：LLM 确认面板（confirm 节点）──
const confirmChoices = ref<Record<string, string>>({})
function setConfirmChoice(id: string, v: string) {
  confirmChoices.value = { ...confirmChoices.value, [id]: v }
}
const hasConfirmIgnore = computed(() =>
  Object.values(confirmChoices.value).some((v) => v === 'ignore'),
)
watch(() => analysisConfirm.value, (pc) => {
  confirmChoices.value = {}
  if (pc?.items?.length) {
    const def = pc.default || 'accept'
    pc.items.forEach((it) => { confirmChoices.value[it.id] = def })
  }
  nextTick(scrollToBottom)
})
function onConfirmSubmit() {
  if (!Object.keys(confirmChoices.value).length) return
  confirmAnalysis({ ...confirmChoices.value })
}
function onAcceptAll() {
  acceptAllAnalysis()
}

// ── 需求分析：BOM 详情抽屉 ──
const drawerOpen = ref(false)
const drawerPlan = ref<Plan | null>(null)
const drawerCfg = ref<PlanLiveCfg | null>(null)
const drawerLoading = ref(false)
async function viewDetail(p: Plan) {
  drawerPlan.value = p
  drawerCfg.value = null
  drawerLoading.value = true
  drawerOpen.value = true
  try {
    drawerCfg.value = await buildPlanCfg(p)
  } finally {
    drawerLoading.value = false
  }
}

// ── 需求分析：转报价单（需会话绑定商机；逻辑与商机详情页 confirmPlan 同源）──
const convertingId = ref<number | null>(null)
async function convertPlan(plan: Plan) {
  const oid = currentThread.value?.opportunity_id
  if (!oid) {
    antMessage.warning('该会话未绑定商机，无法转为报价单')
    return
  }
  convertingId.value = plan.config_id
  try {
    const res = await quotationApi.create({
      opportunity_id: oid,
      quotation_name: `方案-${plan.name || plan.model}`,
    })
    const quotationId = res.quotation_id
    const liveCfg = await buildPlanCfg(plan)
    const picks: Record<string, any> = {
      base_config_id: plan.config_id,
      // 服务器型号 id：机箱卡按它匹配目录机型（形态/用途/型号都从机型对象读）
      server_model_id: plan.server_model_id ?? null,
      bom_source: liveCfg.bom_source,
      l6_custom_price: plan.summary.l6_cost ?? 0,
      l6_profit_margin: 10,
      // IO 选配随 picks 持久化：机箱配置器按机型标准 riser 回填 IO 数量（与 BOM 同源）
      picks: liveCfg.rear ? { rear: liveCfg.rear } : undefined,
    }
    if (liveCfg.bom_source === 'live') {
      picks.bom_template = liveCfg.bom_template
      picks.bom_context = liveCfg.bom_context
    } else {
      picks.bom_excel_rows = liveCfg.bom_excel_rows
    }
    const payload = {
      items: liveCfg.items,
      config_quantities: { CFG1: 1 },
      config_server_models: { CFG1: plan.model || '' },
      config_l6_picks: { CFG1: picks },
    }
    await quotationApi.saveItems(quotationId, payload as any)
    quotationApi.update(quotationId, { source: 'reasoning' }).catch(() => {})
    antMessage.success(`已转为报价单：${plan.name || plan.model}`)
    disconnectWs()
    router.push(`/workspace?opportunityId=${oid}&quotationId=${quotationId}&mode=edit&from=assistant`)
  } catch (e: any) {
    antMessage.error('转为报价单失败：' + (e?.message || e))
  } finally {
    convertingId.value = null
  }
}

async function onNewThread() {
  await newThread()
}

function onDeleteThread(id: string) {
  Modal.confirm({
    title: '删除该会话？',
    content: '将移除该会话及其全部消息。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      await removeThread(id)
    },
  })
}
</script>

<style scoped>
.assistant-panel {
  position: fixed;
  right: 24px;
  bottom: 88px;
  width: 380px;
  height: 560px;
  max-height: calc(100vh - 120px);
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, 0.92));
  backdrop-filter: blur(var(--cpq-glass-blur-3, 16px));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3, 16px));
  border: 1px solid var(--cpq-glass-border);
  border-radius: 16px;
  box-shadow: 0 12px 40px var(--cpq-shadow-color-strong, rgba(0, 0, 0, 0.25));
  z-index: 1500;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ap-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: move;
  user-select: none;
}
.ap-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.ap-title :deep(.anticon) {
  color: var(--cpq-accent-primary);
}
.ap-ctx {
  font-size: 11px;
  color: var(--cpq-text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-ctx-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-accent-success, #52c41a);
  flex-shrink: 0;
}
.ap-ctx-none {
  color: var(--cpq-text-muted);
}
.ap-ctx-none .ap-ctx-dot {
  background: var(--cpq-text-muted);
}
.ap-close {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.ap-close:hover {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-primary);
}

.ap-threads {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w4);
  align-items: center;
}
.ap-thread-select {
  flex: 1;
  min-width: 0;
}
.thread-opt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.thread-opt-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-opt-del {
  color: var(--cpq-text-muted);
  font-size: 12px;
  padding: 2px;
  flex-shrink: 0;
  cursor: pointer;
}
.thread-opt-del:hover {
  color: var(--cpq-accent-danger);
}

.ap-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  min-height: 0;
}
.ap-quick {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid var(--cpq-overlay-w4);
}
.ap-quick-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--cpq-overlay-w15);
  border-radius: 999px;
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.ap-quick-chip:hover:not(:disabled) {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}
.ap-quick-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ap-quick-icon {
  font-size: 12px;
}
.ap-spin {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
.ap-msg-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ap-msg {
  display: flex;
}
.role-user {
  justify-content: flex-end;
}
.role-assistant,
.role-system {
  justify-content: flex-start;
}
.ap-bubble {
  max-width: 82%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}
.role-user .ap-bubble {
  background: var(--cpq-accent-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.role-assistant .ap-bubble {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-primary);
  border: 1px solid var(--cpq-overlay-w6);
  border-bottom-left-radius: 4px;
}
.role-system .ap-bubble {
  background: transparent;
  color: var(--cpq-text-muted);
  font-style: italic;
  font-size: 12px;
}
.ap-cursor {
  display: inline-block;
  animation: ap-blink 1s steps(2, start) infinite;
  color: var(--cpq-accent-primary);
  margin-left: 1px;
}
@keyframes ap-blink {
  to {
    visibility: hidden;
  }
}
.ap-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
}
.ap-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  animation: ap-typing-bounce 1.2s infinite ease-in-out;
}
.ap-typing i:nth-child(2) {
  animation-delay: 0.15s;
}
.ap-typing i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes ap-typing-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

.ap-input {
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w6);
  display: flex;
  gap: 8px;
  align-items: flex-end;
  background: var(--cpq-overlay-w3);
}

/* ── 需求分析：步骤时间线 ── */
.ap-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 2px 0;
}
.ap-step {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w8);
  white-space: nowrap;
}
.ap-step.st-running {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
}
.ap-step.st-done {
  color: var(--cpq-text-secondary);
}
.ap-step.st-error {
  color: var(--cpq-accent-danger);
  border-color: var(--cpq-accent-danger);
}
.ap-plan-card {
  max-width: 100%;
}
.ap-bubble.err {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10);
  border-color: var(--cpq-overlay-danger15);
}

/* ── 需求分析：反问回复区 ── */
.ap-reply-footer {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w8);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ap-reply-q {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--cpq-text-primary);
  white-space: pre-wrap;
}
.ap-format {
  white-space: pre-line;
  padding: 6px 8px;
  background: var(--cpq-overlay-w4);
  border: 1px dashed var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm, 8px);
  color: var(--cpq-text-secondary);
}
.ap-reply-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ap-reply-opt {
  cursor: pointer;
  margin: 0;
}
.ap-reply-input {
  border-radius: var(--cpq-radius-sm, 8px);
}
.ap-reply-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ── 需求分析：LLM 确认面板 ── */
.ap-confirm-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--cpq-overlay-w8);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 45%;
  overflow-y: auto;
}
.ap-confirm-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.ap-confirm-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-a4);
}
.ap-confirm-item.accepted {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
}
.ap-confirm-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}
.ap-confirm-label { font-weight: 600; color: var(--cpq-text-primary); }
.ap-confirm-tag { margin-inline-end: 0 !important; }
.ap-confirm-v { color: var(--cpq-text-secondary); }
.ap-confirm-v.llm { color: var(--cpq-accent-primary); }
.ap-confirm-conf { color: var(--cpq-text-muted); }
.ap-confirm-opts { display: flex; gap: 6px; flex-shrink: 0; }
.ap-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

/* ── 需求分析：BOM 抽屉 / 发起弹窗 ── */
.ap-bom-wrap { display: flex; flex-direction: column; height: 100%; }
.ap-bom-summary {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  padding: 0 0 10px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
  margin-bottom: 10px;
}
.ap-analyze-bar {
  padding: 6px 12px;
  border-top: 1px solid var(--cpq-overlay-w8);
  background: var(--cpq-accent-soft);
}
.ap-analyze-bar-tip {
  font-size: 12px;
  line-height: 1.5;
  color: var(--cpq-accent-primary);
}
.ap-quick-chip.primary {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
  font-weight: 600;
}
.ap-quick-chip.primary:hover:not(:disabled) {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}
.ap-quick-chip.primary.active {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-primary);
  color: #fff;
}

.assistant-panel-enter-active,
.assistant-panel-leave-active {
  transition: opacity 0.25s ease, transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.assistant-panel-enter-from,
.assistant-panel-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}
</style>
