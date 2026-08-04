<template>
  <section class="reasoning-panel glass">
    <header class="rp-head">
      <span class="rp-head-icon"><RobotOutlined /></span>
      <span class="rp-head-title">推理过程</span>
      <span class="rp-head-status" :class="statusClass">{{ statusText }}</span>
      <a-button
        v-if="hasActivity"
        size="small"
        type="text"
        class="rp-restart"
        @click="emit('restart')"
      >
        <template #icon><RedoOutlined /></template>
        重新开始
      </a-button>
    </header>

    <div class="rp-feed" ref="feedRef">
      <!-- 起始空态 -->
      <p v-if="!steps.length && !error && !running" class="rp-empty">
        点「生成报价」，我帮你拆需求、选机型、配 KP、出整机方案。
      </p>

      <!-- 对话消息流：intro + 每步完成弹出一条 + 方案 + 二期脚注 -->
      <template v-for="m in messages" :key="m.key">
        <p v-if="m.kind === 'text' && !m.muted" class="rp-bubble">{{ m.text }}</p>
        <p v-else-if="m.kind === 'text' && m.muted" class="rp-note">{{ m.text }}</p>
        <p v-else-if="m.kind === 'user'" class="rp-bubble user">{{ m.text }}</p>
        <PlanCard v-else-if="m.kind === 'plan' && m.plan" :plan="m.plan" @view-bom="viewDetail(m.plan)">
          <template #extra-actions>
            <a-button
              type="primary"
              size="small"
              :loading="confirmingId === m.plan.config_id"
              @click="onConfirm(m.plan)"
            >
              <template #icon><ArrowRightOutlined /></template>
              确认转为报价单
            </a-button>
          </template>
        </PlanCard>
      </template>

      <!-- 思考中：打字指示 -->
      <div v-if="showTyping" class="rp-typing"><i></i><i></i><i></i></div>

      <!-- 失败 -->
      <p v-if="error" class="rp-bubble err"><ExclamationCircleOutlined /> {{ error }}</p>
    </div>

    <!-- 反问回复区（ask_user 节点触发，pipeline 暂停等用户补齐） -->
    <div v-if="pendingPrompt" class="rp-reply-footer">
      <p v-if="pendingPrompt.format" class="rp-note rp-format">{{ pendingPrompt.format }}</p>
      <div v-if="pendingPrompt.options?.length" class="rp-reply-options">
        <a-tag v-for="opt in pendingPrompt.options" :key="opt" class="rp-reply-opt" @click="quickReply(opt)">{{ opt }}</a-tag>
      </div>
      <a-textarea
        v-model:value="replyText"
        :auto-size="{ minRows: 1, maxRows: 4 }"
        :placeholder="replyPlaceholder"
        class="rp-reply-input"
        @press-enter="onEnter"
      />
      <div class="rp-reply-actions">
        <a-button size="small" @click="onSkip">跳过</a-button>
        <a-button type="primary" size="small" :disabled="!replyText.trim()" @click="submitReply">
          <template #icon><ArrowRightOutlined /></template>
          发送
        </a-button>
      </div>
    </div>

    <!-- LLM 确认面板（confirm 节点触发：冲突/低置信度项，默认采纳、高亮可改） -->
    <div v-if="pendingConfirm" class="rp-confirm-footer">
      <p class="rp-confirm-title"><BulbOutlined /> {{ pendingConfirm.question || '大模型补充了以下信息，默认已采纳，可改为「忽略」后重新生成：' }}</p>
      <div v-for="it in pendingConfirm.items" :key="it.id" class="rp-confirm-item" :class="{ accepted: (confirmChoices[it.id] || 'accept') === 'accept' }">
        <div class="rp-confirm-info">
          <span class="rp-confirm-label">{{ it.label }}</span>
          <a-tag v-if="it.level === 'conflict'" color="orange" class="rp-confirm-tag">与规则冲突</a-tag>
          <a-tag v-else color="blue" class="rp-confirm-tag">低置信度</a-tag>
          <span v-if="it.rule != null" class="rp-confirm-v">规则：{{ it.rule }}</span>
          <span class="rp-confirm-v llm">LLM：{{ it.llm || '—' }}</span>
          <span v-if="it.confidence != null" class="rp-confirm-conf">置信 {{ Math.round(it.confidence * 100) }}%</span>
        </div>
        <div class="rp-confirm-opts">
          <a-button
            size="small"
            :type="(confirmChoices[it.id] || 'accept') === 'accept' ? 'primary' : 'default'"
            @click="setConfirmChoice(it.id, 'accept')"
          >采纳</a-button>
          <a-button
            size="small"
            :type="(confirmChoices[it.id] || 'accept') === 'ignore' ? 'danger' : 'default'"
            @click="setConfirmChoice(it.id, 'ignore')"
          >忽略</a-button>
        </div>
      </div>
      <div class="rp-confirm-actions">
        <a-button size="small" @click="onConfirmAcceptAll">全部采纳，查看方案</a-button>
        <a-button type="primary" size="small" :disabled="!hasConfirmIgnore" @click="onConfirmSubmit">
          按以上选择重新生成
        </a-button>
      </div>
      <p class="rp-note" style="margin-top:6px">「全部采纳」直接看当前方案（不重跑 LLM）；改了选择才重新生成。</p>
    </div>

    <!-- BOM 详情抽屉（复用工作台 BomTable，L6 走基准配置的 BOM 模板格式） -->
    <a-drawer
      v-model:open="drawerOpen"
      :title="drawerPlan?.name || '整机 BOM 详情'"
      placement="right"
      width="560"
      class="rp-bom-drawer"
    >
      <div class="rp-bom-wrap" v-if="drawerPlan">
        <div class="rp-bom-summary">
          {{ [drawerPlan.series, drawerPlan.form, drawerPlan.bays != null ? `${drawerPlan.bays}盘位` : ''].filter(Boolean).join(' · ') }}
          · 底盘 {{ drawerPlan.summary.parts_count }} 件 + KP {{ drawerPlan.summary.kp_count }} 件
        </div>
        <a-spin :spinning="drawerLoading" tip="转 BOM 模板格式…">
          <BomTable v-if="drawerCfg" :cfg="drawerCfg" />
        </a-spin>
      </div>
    </a-drawer>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import {
  RobotOutlined, ExclamationCircleOutlined, ArrowRightOutlined, RedoOutlined, BulbOutlined,
} from '@ant-design/icons-vue'
import BomTable from '@/components/BomTable.vue'
import PlanCard from '@/components/reasoning/PlanCard.vue'
import type { Plan } from '@/api/reasoning'
import type { ReasoningStep, ConfirmItem } from '@/composables/useReasoningStream'
import { FUTURE_STEPS } from '@/composables/useReasoningStream'
import { buildPlanCfg, type PlanLiveCfg } from '@/composables/usePlanBom'
import { STEP_COPY } from '@/utils/reasoningStepCopy'

const props = defineProps<{
  steps: ReasoningStep[]
  plans: Plan[]
  running: boolean
  error: string | null
  keywords: string[]
  pendingPrompt?: {
    reply_id: string
    question: string
    missing_fields: string[]
    options: string[]
    round: number
    clarity_capped: boolean
    stage?: string
    format?: string
  } | null
  pendingConfirm?: {
    reply_id: string
    question: string
    items: ConfirmItem[]
    default: string
  } | null
}>()
const emit = defineEmits<{
  (e: 'confirm-plan', plan: Plan): void
  (e: 'user-reply', text: string): void
  (e: 'user-skip'): void
  (e: 'confirm-submit', decisions: Record<string, string>): void
  (e: 'confirm-accept-all'): void
  (e: 'restart'): void
}>()

const confirmingId = ref<number | null>(null)
const drawerOpen = ref(false)
const drawerPlan = ref<Plan | null>(null)
const drawerCfg = ref<PlanLiveCfg | null>(null)
const drawerLoading = ref(false)

// STEP_COPY（每步完成 → AI 口吻摘要）抽到 @/utils/reasoningStepCopy，与试运行面板共用

interface Msg { key: string; kind: 'text' | 'plan' | 'user'; text?: string; muted?: boolean; plan?: Plan }

// 已发送的用户回复（本地累积，重跑不清空——保留对话历史感）
const sentReplies = ref<string[]>([])

const messages = computed<Msg[]>(() => {
  const out: Msg[] = []
  if (props.steps.length) out.push({ key: 'intro', kind: 'text', text: '收到，我来拆解一下你的需求。' })
  for (const s of props.steps) {
    if (s.status !== 'done') continue
    const fn = STEP_COPY[s.key]
    if (fn) out.push({ key: `step-${s.key}`, kind: 'text', text: fn(s.payload) })
  }
  // 用户历轮回复（右对齐气泡，紧跟在 AI 步骤之后、当前反问/方案之前）
  sentReplies.value.forEach((t, i) => {
    out.push({ key: `user-${i}`, kind: 'user', text: t })
  })
  for (const p of props.plans) out.push({ key: `plan-${p.config_id}`, kind: 'plan', plan: p })
  if (props.pendingPrompt) {
    out.push({ key: `prompt-${props.pendingPrompt.reply_id}`, kind: 'text', text: props.pendingPrompt.question })
  }
  if (props.plans.length) {
    const more = FUTURE_STEPS.map((f) => f.label).slice(0, 4).join('、')
    out.push({ key: 'future', kind: 'text', muted: true, text: `接入 LLM 后还能：${more}…` })
  }
  return out
})

const showTyping = computed(() => props.running && !props.error)

// 头部状态：跑哪步就显哪步名
const statusClass = computed(() => {
  if (props.error) return 'err'
  if (props.running) return 'running'
  if (props.plans.length) return 'done'
  return ''
})
const statusText = computed(() => {
  if (props.error) return '失败'
  if (props.running) {
    const cur = props.steps.find((s) => s.status === 'running')
    return cur?.label || '分析中…'
  }
  if (props.plans.length) return `${props.plans.length} 张方案`
  return ''
})

// 自适应滚动到最新消息
const feedRef = ref<HTMLElement | null>(null)
async function scrollBottom() {
  await nextTick()
  if (feedRef.value) feedRef.value.scrollTop = feedRef.value.scrollHeight
}
watch(() => messages.value.length, scrollBottom)
watch(showTyping, (v) => { if (v) scrollBottom() })

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

function onConfirm(p: Plan) {
  confirmingId.value = p.config_id
  emit('confirm-plan', p)
}

// ── 反问回复（ask_user 节点触发，pipeline 暂停等用户补齐）──
/** 面板是否有内容（出现"重新开始"按钮的条件） */
const hasActivity = computed(() =>
  props.steps.length > 0 || props.plans.length > 0 || !!props.pendingPrompt || !!props.pendingConfirm || !!props.error || props.running,
)

const replyText = ref('')
/** 点 chip 即发送（Spec Assistant 式）；防连点锁，下一轮反问到达时解锁 */
const quickLocked = ref(false)
function quickReply(opt: string) {
  if (quickLocked.value) return
  quickLocked.value = true
  sentReplies.value.push(opt)
  replyText.value = ''
  emit('user-reply', opt)
}
const replyPlaceholder = computed(() =>
  props.pendingPrompt?.clarity_capped
    ? '已多次补充，可直接发送或跳过'
    : '回复补充信息，回车发送（Shift+Enter 换行）'
)
function submitReply() {
  const t = replyText.value.trim()
  if (!t) return
  sentReplies.value.push(t)  // 立即显示用户气泡（不等后端 pipeline_start 回来）
  emit('user-reply', t)
  replyText.value = ''
}
function onSkip() {
  emit('user-skip')
  replyText.value = ''
}
function onEnter(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  submitReply()
}
watch(() => props.pendingPrompt, () => {
  quickLocked.value = false
  scrollBottom()
})

// ── LLM 确认面板（confirm 节点：默认采纳、高亮可改）──
const confirmChoices = ref<Record<string, string>>({})
function setConfirmChoice(id: string, v: string) {
  confirmChoices.value = { ...confirmChoices.value, [id]: v }
}
const hasConfirmIgnore = computed(() =>
  Object.values(confirmChoices.value).some((v) => v === 'ignore'),
)
watch(() => props.pendingConfirm, (pc) => {
  confirmChoices.value = {}
  if (pc?.items?.length) {
    const def = pc.default || 'accept'
    pc.items.forEach((it) => { confirmChoices.value[it.id] = def })
  }
  scrollBottom()
})
function onConfirmSubmit() {
  if (!Object.keys(confirmChoices.value).length) return
  emit('confirm-submit', { ...confirmChoices.value })
}
function onConfirmAcceptAll() {
  emit('confirm-accept-all')
}

defineExpose({ stopConfirming: () => { confirmingId.value = null } })
</script>

<style scoped>
.reasoning-panel {
  padding: 14px 16px;
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
  /* 粘顶 + 高度跟随视口（减去上方页头/信息卡/需求卡占位）*/
  position: sticky;
  top: 14px;
  height: clamp(260px, calc(100vh - 400px), 600px);
  max-height: calc(100vh - 28px);
}

/* ── 头部（唯一 AI 标识：一个克制的机器人图标）── */
.rp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
}
.rp-head-icon {
  width: 24px;
  height: 24px;
  border-radius: var(--cpq-radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a10);
}
.rp-head-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.rp-head-status {
  margin-left: auto;
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.rp-head-status.running { color: var(--cpq-accent-primary); }
.rp-head-status.err { color: var(--cpq-accent-danger); }
.rp-restart {
  margin-left: auto;
  color: var(--cpq-text-secondary);
}

/* ── 消息流 ── */
.rp-feed {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}
.rp-empty {
  margin: 12px 0;
  font-size: 12px;
  color: var(--cpq-text-muted);
  text-align: center;
  line-height: 1.6;
}

/* 普通文字气泡（左对齐，白玻璃）*/
.rp-bubble {
  align-self: flex-start;
  flex-shrink: 0;
  max-width: 92%;
  margin: 0;
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-md);
  box-shadow: var(--cpq-shadow-sm);
  animation: rp-in 0.28s var(--cpq-ease-out-expo) both;
}
.rp-bubble.err {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10);
  border-color: var(--cpq-overlay-danger15);
}
/* 用户回复气泡（右对齐，激活色底，区别于 AI 左对齐白玻璃）*/
.rp-bubble.user {
  align-self: flex-end;
  color: var(--cpq-text-on-accent, #fff);
  background: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
}
/* 脚注（无气泡，muted）*/
.rp-note {
  flex-shrink: 0;
  margin: 4px 0 0;
  padding: 0 4px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--cpq-text-muted);
}

/* 整机方案卡样式抽到 @/components/reasoning/PlanCard.vue（.pc-* 前缀）*/

/* 打字指示（三点）*/
.rp-typing {
  align-self: flex-start;
  flex-shrink: 0;
  display: inline-flex;
  gap: 4px;
  padding: 10px 12px;
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-md);
}
.rp-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  animation: rp-dot 1.2s infinite ease-in-out;
}
.rp-typing i:nth-child(2) { animation-delay: 0.2s; }
.rp-typing i:nth-child(3) { animation-delay: 0.4s; }

@keyframes rp-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes rp-dot {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}

/* ── BOM 抽屉 ── */
.rp-bom-wrap { display: flex; flex-direction: column; height: 100%; }
.rp-bom-summary {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  padding: 0 0 10px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
  margin-bottom: 10px;
}

/* ── 反问回复区 ── */
.rp-format {
  white-space: pre-line;
  padding: 6px 8px;
  background: var(--cpq-overlay-w4);
  border: 1px dashed var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm, 8px);
  color: var(--cpq-text-secondary);
}
.rp-reply-footer {
  flex-shrink: 0;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--cpq-overlay-w8);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rp-reply-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.rp-reply-opt {
  cursor: pointer;
  margin: 0;
}
.rp-reply-input {
  border-radius: var(--cpq-radius-sm, 8px);
}
.rp-reply-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ── LLM 确认面板 ── */
.rp-confirm-footer {
  border-top: 1px solid var(--cpq-overlay-w8);
  padding-top: 10px;
  margin-top: 4px;
}
.rp-confirm-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 8px;
}
.rp-confirm-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  margin-bottom: 6px;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-a4);
}
.rp-confirm-item.accepted {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
}
.rp-confirm-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}
.rp-confirm-label { font-weight: 600; color: var(--cpq-text-primary); }
.rp-confirm-tag { margin-inline-end: 0 !important; }
.rp-confirm-v { color: var(--cpq-text-secondary); }
.rp-confirm-v.llm { color: var(--cpq-accent-primary); }
.rp-confirm-conf { color: var(--cpq-text-muted); }
.rp-confirm-opts { display: flex; gap: 6px; flex-shrink: 0; }
.rp-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}
</style>
