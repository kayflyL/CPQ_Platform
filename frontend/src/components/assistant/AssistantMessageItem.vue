<template>
  <div class="am-row" :class="`role-${role}`">
    <template v-if="role !== 'user'">
      <div
        class="am-avatar"
        :class="{ 'am-avatar-has-img': !!author.avatar_url }"
        :style="{ background: author.color || 'var(--cpq-accent-primary, #1677ff)' }"
      >
        <img v-if="author.avatar_url" :src="author.avatar_url" alt="" />
        <span v-else class="am-avatar-initial">{{ avatarInitial(author.name) }}</span>
      </div>
      <div class="am-content">
        <span v-if="showAuthor && author.name" class="am-author">{{ author.name }}</span>
        <!-- 思考过程：Claude Code 式多行增长暗色块——限高内部滚动自动跟底 -->
        <div v-if="thinking" class="am-thinking" :class="{ 'am-thinking--live': thinkingActive }">
          <span class="am-thinking-dot" />
          <span ref="thinkTextEl" class="am-thinking-text">{{ thinkingTail }}</span>
        </div>
        <!-- 结构化问题面板：任务进行中向用户要决定（选项卡数据=引擎缺口，文案=角色）。
             答完即收（Claude Code 语义）：未答时渲染整卡（回合进行中渲染但禁点，卡到达即可见）；
             已答/被取代 → 塌成一行静态记录（问题 + 已选答案），选项列表不留在聊天流里。 -->
        <div v-if="question && !optionAnswered" class="am-q" :class="{ 'am-q--locked': !optionInteractive }">
          <div class="am-q-head">
            <span class="am-q-badge">?</span>
            <span class="am-q-text">{{ question.text }}</span>
          </div>
          <template v-for="(opt, i) in question.options" :key="`${opt.slot}-${opt.value}`">
            <div v-if="isGroupStart(i)" class="am-q-group-label">
              <span>{{ opt.group }}</span>
              <a-select
                v-if="isPartsCard && props.threadId"
                class="am-q-pick-select"
                size="small"
                show-search
                allow-clear
                :disabled="!optionInteractive"
                placeholder="从配件库自选…"
                :value="undefined"
                :open="pickOpen[opt.slot]"
                :loading="!!pickLoading[opt.slot]"
                :options="pickSelectOptions(opt.slot)"
                :filter-option="filterPickOption"
                @dropdownVisibleChange="(o: boolean) => setPickOpen(opt.slot, o)"
                @change="(v: any) => onPickSelect(opt.slot, v)"
                @blur="setPickOpen(opt.slot, false)"
              />
            </div>
            <div v-if="isGroupStart(i) && pickError[opt.slot]" class="am-q-pick-err">{{ pickError[opt.slot] }}</div>
            <button
              type="button"
              class="am-q-opt"
              :class="{ 'am-q-opt--picked': isPicked(opt), 'am-q-opt--escape': isEscape(opt), 'am-q-opt--rec': opt.recommended }"
              :disabled="!optionInteractive"
              @click="onOptClick(opt)"
            >
              <span class="am-q-key">{{ isPicked(opt) ? '✓' : i + 1 }}</span>
              <span class="am-q-body">
                <span class="am-q-label">{{ opt.label }}<span v-if="opt.recommended" class="am-q-rec">推荐</span></span>
                <span v-if="opt.desc" class="am-q-desc">{{ opt.desc }}</span>
              </span>
            </button>
          </template>
          <!-- 数量 stepper：选中项可调数量时出现，实时显示总量（数量是参数，服务端 clamp） -->
          <div v-if="stepperVisible" class="am-q-stepper">
            <span class="am-q-stepper-label">数量</span>
            <button type="button" class="am-q-step-btn" :disabled="qtyVal <= 1" @click="qtyVal = Math.max(1, qtyVal - 1)">−</button>
            <input
              class="am-q-step-input"
              type="number"
              min="1"
              :max="qtyMax"
              v-model.number="qtyVal"
              @blur="clampQty"
            />
            <button type="button" class="am-q-step-btn" :disabled="qtyVal >= qtyMax" @click="qtyVal = Math.min(qtyMax, qtyVal + 1)">＋</button>
            <span v-if="totalText" class="am-q-stepper-total">{{ totalText }}</span>
          </div>
          <!-- 手动输入型号：自由型号走服务端目录模糊匹配，库外型号白盒提交 -->
          <div v-if="isPartsCard" class="am-q-manual">
            <input
              v-model="manualText"
              class="am-q-manual-input"
              :disabled="!optionInteractive"
              placeholder="手动输入型号（库外型号也可提交）"
              @keyup.enter="submitParts"
            />
          </div>
          <div class="am-q-foot">
            <template v-if="isPartsCard && question.options.length">
              <span class="am-q-form-hint">{{ partsHint }}</span>
              <button
                type="button"
                class="am-q-submit"
                :disabled="!canSubmitParts"
                @click="submitParts"
              >确认提交</button>
            </template>
            <template v-else-if="question.options.length">选择一项，或直接输入其他回答</template>
            <template v-else>直接输入你的回答</template>
          </div>
        </div>
        <!-- 已答/被取代：一行静态记录，聊天流只留问题与答案 -->
        <div v-else-if="question" class="am-q-done">
          <span class="am-q-done-check">✓</span>
          <span class="am-q-done-text">{{ question.text || '问题' }}</span>
          <span class="am-q-done-answer">{{ collapsedAnswer }}</span>
        </div>
        <!-- 实时气泡：流式正文 > 状态行 > 呼吸点；正文已流出时若工具在跑，状态行挂在正文下方 -->
        <div v-else class="am-bubble am-bubble--live">
          <template v-if="content || streaming">
            {{ content }}<span v-if="streaming" class="am-cursor">▍</span>
            <span v-if="statusText" class="am-status-line am-status-under"><span class="am-status-dot"></span>{{ statusText }}</span>
          </template>
          <template v-else-if="statusText">
            <span class="am-status-line"><span class="am-status-dot"></span>{{ statusText }}</span>
          </template>
          <template v-else-if="idleText">
            <span class="am-status-line"><span class="am-status-dot"></span>{{ idleText }}</span>
          </template>
          <template v-else>
            <span class="am-typing"><i></i><i></i><i></i></span>
          </template>
        </div>
      </div>
    </template>
    <div v-else class="am-bubble">{{ content }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { assistantApi } from '@/api/assistant'

const props = withDefaults(defineProps<{
  message?: {
    role?: string
    content?: string
    kind?: string
    data?: string
  }
  author?: {
    name?: string
    avatar_url?: string
    color?: string
  }
  streaming?: boolean
  typing?: boolean
  statusText?: string
  /** 静默心跳文案（父组件计时）：三条流全空时替呼吸点显示「模型思考中 Ns…」 */
  idleText?: string
  thinking?: string
  thinkingActive?: boolean
  /** 问题面板是否可点：已答/被取代或回合进行中为 false（父组件按消息序+运行态计算） */
  optionInteractive?: boolean
  /** 选项卡是否已被回答/取代（父组件按消息序计算）：塌成一行静态记录。
   *  与 optionInteractive 分离：回合进行中卡片可见但禁点，不再整卡消失 */
  optionAnswered?: boolean
  /** 当前会话 ID：配件库自选候选按它查询（card-pick 端点读留底卡） */
  threadId?: string
  /** 发卡角色（浮动面板会话可被分派，记忆按角色存）：留空走线程默认 */
  pickRole?: string
  /** 是否显示作者名：群聊/转接才显示（单人格 DM 常驻省略） */
  showAuthor?: boolean
}>(), {
  message: undefined,
  author: () => ({ name: 'AI', avatar_url: '', color: '' }),
  streaming: false,
  typing: false,
  statusText: '',
  idleText: '',
  thinking: '',
  thinkingActive: false,
  optionInteractive: true,
  optionAnswered: false,
  threadId: '',
  pickRole: '',
  showAuthor: true,
})

const emit = defineEmits<{
  (e: 'select-option', value: string, slot?: string): void
  (e: 'submit-selections', selections: Array<{ slot: string; value: string; label: string; qty?: number }>): void
}>()

// Claude Code 式思考块：多行增长（保留换行），限长尾部 + 块内自动跟底
const thinkingTail = computed(() => {
  const t = (props.thinking || '').trim()
  if (!t) return '思考中…'
  return t.length > 1600 ? '…' + t.slice(-1600) : t
})
const thinkTextEl = ref<HTMLElement | null>(null)
watch(() => props.thinking, async () => {
  await nextTick()
  const el = thinkTextEl.value
  if (el) el.scrollTop = el.scrollHeight
})
const role = computed(() => props.message?.role === 'user' ? 'user' : 'assistant')
const content = computed(() => props.message?.content || '')

interface QOption {
  label: string
  value: string
  desc: string
  slot: string
  group: string
  qty?: number
  qty_max?: number
  unit_gb?: number
  recommended?: boolean
}

const question = computed<null | {
  text: string
  slot: string
  options: QOption[]
  partsCard: boolean
  unitLabel: string
}>(() => {
  if (props.message?.kind !== 'input_options' || !props.message?.data) return null
  try {
    const data = JSON.parse(props.message.data)
    const text = String(props.message?.content || data?.question || '').trim()
    const slotOptions: Record<string, any[]> = data?.slot_options || {}
    let options: QOption[] = []
    for (const [slot, arr] of Object.entries(slotOptions)) {
      if (!Array.isArray(arr) || !arr.length) continue
      options = options.concat(arr.map((o: any) => ({
        label: String(o?.label ?? o?.value ?? ''),
        value: String(o?.value ?? o?.label ?? ''),
        desc: String(o?.desc || ''),
        // 逐项配件卡选项各落自己的信号槽（后端单组下发）；普通卡退回字典键
        slot: String(o?.slot || slot),
        group: String(o?.group || ''),
        qty: Number.isFinite(o?.qty) && o.qty > 0 ? Number(o.qty) : undefined,
        qty_max: Number.isFinite(o?.qty_max) && o.qty_max > 0 ? Number(o.qty_max) : undefined,
        unit_gb: Number.isFinite(o?.unit_gb) && o.unit_gb > 0 ? Number(o.unit_gb) : undefined,
        recommended: !!o?.recommended,
      })))
    }
    if (!options.length && Array.isArray(data?.options)) {
      const slot = 'general'
      options = data.options.map((o: any) => ({
        label: String(o?.label ?? o?.value ?? o ?? ''),
        value: String(o?.value ?? o?.label ?? o ?? ''),
        desc: String(o?.desc || ''),
        slot,
        group: '',
      }))
    }
    options = options.filter((o) => o.label)
    if (!text && !options.length) return null
    // 卡能力声明制（2026-09-06 插头化）：是否表单卡（自选/步进/手动/提交）由后端
    // payload 声明驱动，前端不再枚举业务槽位词
    return { text, slot: options[0]?.slot || 'general', options,
             partsCard: !!data?.parts_card, unitLabel: String(data?.unit_label || '') }
  } catch {
    return null
  }
})

function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

// ── 逐项配件卡：单组选项=选择→（可调数量时）stepper→提交；组头挂配件库下拉 ──
// 卡能力声明制（2026-09-06 插头化）：表单模式由 payload 的 parts_card 声明驱动，
// 前端不再枚举业务槽位词（旧 pickableSlots gpu/cpu/memory/storage 已删）。
const picked = ref<QOption | null>(null)
const qtyVal = ref(0)
const manualText = ref('')

const partsSlot = computed<string>(() => {
  if (!question.value?.partsCard) return ''
  const slots = new Set(question.value?.options.map((o) => o.slot) || [])
  return slots.size === 1 ? [...slots][0] : ''
})

const isPartsCard = computed(() => !!partsSlot.value && !!(question.value?.options.length))

const adjustable = computed(() => {
  const opts = question.value?.options.filter((o) => o.slot === partsSlot.value) || []
  return opts.some((o) => o.qty && o.qty_max)
})

const activeQtyMax = computed(() => {
  const opts = question.value?.options.filter((o) => o.slot === partsSlot.value) || []
  return picked.value?.qty_max || opts.find((o) => o.qty_max)?.qty_max || 0
})

const qtyMax = computed(() => Math.max(1, activeQtyMax.value || 1))

const stepperVisible = computed(() =>
  optionInteractiveOn() && adjustable.value && (picked.value || manualText.value.trim()) && activeQtyMax.value > 0)

function optionInteractiveOn(): boolean {
  return !!props.optionInteractive
}

function isEscape(o: QOption): boolean {
  return o.slot === 'kp_scenario_done' || o.slot === 'kp_scenario_skip' || o.value === 'scenario_complete' || o.value === 'skip_group'
}

function isPicked(o: QOption): boolean {
  return !!picked.value && picked.value.slot === o.slot && picked.value.value === o.value
}

// 已答卡的一行记录：优先显示选了什么（含数量）；未被本卡作答（答了兄弟卡/打字
// 覆盖、记忆丢失刷新后）退「已收起」——不能说「已处理」，用户没碰过这张卡
const collapsedAnswer = computed(() => {
  const t = manualText.value.trim()
  if (t) return `已选：${t}`
  if (picked.value) {
    const qty = adjustable.value && qtyVal.value > 1 ? ` ×${qtyVal.value}` : ''
    return `已选：${picked.value.label}${qty}`
  }
  return '已收起'
})

const partsHint = computed(() => {
  if (manualText.value.trim()) return '按输入型号提交（服务端自动匹配目录）'
  if (picked.value) return adjustable.value ? '已选，可调数量后提交' : '已选，确认提交'
  return '选择一个推荐项，或从配件库/手动输入型号'
})

const canSubmitParts = computed(() =>
  optionInteractiveOn() && !!(picked.value || manualText.value.trim()))

function onOptClick(o: QOption) {
  if (!props.optionInteractive) return
  if (!isPartsCard.value || isEscape(o) || !adjustable.value) {
    // 非逐项卡/逃生项/无数量维度：即点即发（点击=回答）。先记下 picked——
    // 答完即锁后卡上仍能看到选了哪项（✓ 留在原卡，Claude Code 答案留痕）
    picked.value = o
    emit('select-option', o.value, o.slot)
    return
  }
  if (isPicked(o)) {
    picked.value = null
  } else {
    picked.value = o
    qtyVal.value = o.qty || 1
  }
}

function clampQty() {
  if (!Number.isFinite(qtyVal.value) || qtyVal.value < 1) qtyVal.value = 1
  qtyVal.value = Math.min(qtyMax.value, Math.max(1, Math.round(qtyVal.value)))
}

function fmtGB(gb: number): string {
  return gb >= 1024 && gb % 1024 === 0 ? `${gb / 1024}T` : gb >= 1024 ? `${(gb / 1024).toFixed(1)}T` : `${gb}G`
}

const totalText = computed(() => {
  const unit = picked.value?.unit_gb
  if (!unit) return ''
  const total = (qtyVal.value || 0) * unit
  const suffix = question.value?.unitLabel ? ` ${question.value.unitLabel}` : ''
  return `共 ${fmtGB(total)}${suffix}`
})

function submitParts() {
  if (!canSubmitParts.value || !partsSlot.value) return
  const text = manualText.value.trim()
  if (text) {
    emit('submit-selections', [{
      slot: partsSlot.value, value: text, label: text,
      ...(stepperVisible.value ? { qty: qtyVal.value } : {}),
    }])
    return
  }
  if (picked.value) {
    emit('submit-selections', [{
      slot: picked.value.slot, value: picked.value.value, label: picked.value.label,
      ...(stepperVisible.value ? { qty: qtyVal.value } : {}),
    }])
  }
}

// ── 配件库自选：组头下拉（远程加载候选并登记进留底卡，选中即当前选择） ──
const pickOpen = ref<Record<string, boolean>>({})
const pickLoading = ref<Record<string, boolean>>({})
const pickOptions = ref<Record<string, QOption[]>>({})
const pickError = ref<Record<string, string>>({})

function isGroupStart(i: number): boolean {
  const opts = question.value?.options || []
  const g = opts[i]?.group || ''
  return !!g && (i === 0 || (opts[i - 1]?.group || '') !== g)
}

async function loadPick(slot: string) {
  if (pickLoading.value[slot] || pickOptions.value[slot]?.length || !props.threadId) {
    pickOpen.value[slot] = true
    return
  }
  pickLoading.value[slot] = true
  pickError.value[slot] = ''
  try {
    const res = await assistantApi.threads.cardPick(props.threadId, slot, props.pickRole || undefined)
    pickOptions.value[slot] = (res.options || []).map((o) => ({
      label: String(o.label || o.value || ''),
      value: String(o.value || o.label || ''),
      desc: String(o.desc || ''),
      slot: String(o.slot || slot),
      group: String(o.group || ''),
      qty: Number.isFinite(o?.qty) && Number(o.qty) > 0 ? Number(o.qty) : undefined,
      qty_max: Number.isFinite(o?.qty_max) && Number(o.qty_max) > 0 ? Number(o.qty_max) : undefined,
    }))
  } catch (e: any) {
    pickError.value[slot] = e?.response?.data?.detail || '配件库查询失败，请稍后再试'
  } finally {
    pickLoading.value[slot] = false
  }
}

/** 自选下拉开合受控：点外/blur/选中后关闭（旧版 :open 永远钉死 true=关不上） */
function setPickOpen(slot: string, open: boolean) {
  pickOpen.value[slot] = open
  if (open) void loadPick(slot)
}

function pickSelectOptions(slot: string) {
  return (pickOptions.value[slot] || []).map((o) => ({
    value: o.value,
    label: o.label,
  }))
}

function filterPickOption(input: string, option: any): boolean {
  return String(option?.label || '').toLowerCase().includes(String(input || '').toLowerCase())
}

function onPickSelect(slot: string, value: any) {
  if (!value) return
  const o = (pickOptions.value[slot] || []).find((x) => x.value === value)
  if (!o) return
  picked.value = o
  qtyVal.value = Math.min(qtyMax.value, partsSlot.value === 'storage' ? 2 : qtyMax.value)
  pickOpen.value[slot] = false
}
</script>

<style scoped>
.am-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.role-user {
  justify-content: flex-end;
}

.role-assistant,
.role-system {
  justify-content: flex-start;
}

.am-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677ff);
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
}

.am-avatar-initial {
  line-height: 1;
}

.am-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.am-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  max-width: calc(100% - 38px);
}

.am-author {
  font-size: 12px;
  line-height: 1.2;
  color: var(--cpq-text-muted);
  margin-bottom: 4px;
}

/* 思考过程：Claude Code 式单行动态刷新（实时显示思考尾部片段） */
.am-thinking {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: 82%;
  margin-bottom: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  border: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.12));
  font-size: 12px;
  line-height: 18px;
  color: var(--cpq-text-secondary, #a6adb4);
  opacity: .9;
}
.am-thinking-dot {
  flex: none;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: currentColor;
}
.am-thinking--live .am-thinking-dot {
  animation: am-think-pulse 1.2s ease-in-out infinite;
}
.am-thinking--live {
  opacity: 1;
}
.am-thinking-text {
  min-width: 0;
  display: block;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 138px;
  overflow-y: auto;
  scrollbar-width: thin;
}
@keyframes am-think-pulse {
  0%, 100% { opacity: .35; transform: scale(.85); }
  50% { opacity: 1; transform: scale(1.1); }
}

/* ── 结构化问题面板（Claude Code 式：题头 + 竖排选项 + 序号 + 描述） ── */
.am-q {
  max-width: 82%;
  min-width: 240px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.12));
  border-radius: 12px;
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
/* 回合进行中：卡可见但禁点（半透明提示稍候），与已答塌行是两个语义 */
.am-q--locked {
  opacity: .62;
}
.am-q-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w8, rgba(255,255,255,.10));
  background: var(--cpq-overlay-a6, rgba(22,119,255,.06));
}
.am-q-badge {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--cpq-accent-primary, #1677ff);
  border: 1px solid var(--cpq-accent-primary, #1677ff);
  margin-top: 1px;
}
.am-q-text {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--cpq-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.am-q-group-label {
  padding: 8px 12px 4px;
  font-size: 11px;
  color: var(--cpq-text-muted, #8c8c8c);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.am-q-pick-select {
  flex: none;
  width: 200px;
  font-size: 12px;
}
.am-q-pick-err {
  padding: 4px 12px 0;
  font-size: 11.5px;
  color: var(--cpq-danger, #ff4d4f);
}
.am-q-opt {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  border: 0;
  border-top: 1px solid transparent;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background .15s ease;
}
.am-q-opt + .am-q-opt,
.am-q-group-label + .am-q-opt {
  border-top: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.08));
}
.am-q-opt:hover {
  background: var(--cpq-overlay-a8, rgba(22,119,255,.10));
}
.am-q-opt:disabled {
  cursor: default;
}
/* 逐项卡选中态：蓝边 + 微底色，勾选符在 am-q-key 里 */
.am-q-opt--picked {
  background: var(--cpq-overlay-a8, rgba(22,119,255,.10));
  box-shadow: inset 2px 0 0 var(--cpq-accent-primary, #1677ff);
}
.am-q-opt--picked .am-q-key {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
/* 逃生项（「就这些」/「先跳过这组」）：收尾动作非单选，弱化为文字按钮观感 */
.am-q-opt--escape .am-q-label {
  color: var(--cpq-text-secondary, #a6adb4);
}
/* 大脑推荐标记（推荐制）：AI 给出推断倾向的选项 */
.am-q-rec {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 10.5px;
  line-height: 18px;
  vertical-align: middle;
  color: #6ea8ff;
  background: rgba(22, 119, 255, 0.14);
  border: 1px solid rgba(22, 119, 255, 0.35);
}
.am-q-opt--rec {
  border-color: rgba(22, 119, 255, 0.45);
}
/* 数量 stepper + 实时总量 */
.am-q-stepper {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.08));
  background: var(--cpq-overlay-w2, rgba(255,255,255,.02));
  font-size: 12px;
}
.am-q-stepper-label {
  color: var(--cpq-text-muted, #8c8c8c);
}
.am-q-step-btn {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.14));
  background: transparent;
  color: var(--cpq-text-primary);
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.am-q-step-btn:disabled {
  opacity: .4;
  cursor: default;
}
.am-q-step-btn:not(:disabled):hover {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
.am-q-step-input {
  width: 56px;
  height: 22px;
  border-radius: 6px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.14));
  background: transparent;
  color: var(--cpq-text-primary);
  font-size: 12px;
  text-align: center;
  -moz-appearance: textfield;
}
.am-q-step-input::-webkit-outer-spin-button,
.am-q-step-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.am-q-stepper-total {
  margin-left: 4px;
  color: var(--cpq-accent-primary, #1677ff);
  font-weight: 600;
}
/* 手动输入型号 */
.am-q-manual {
  padding: 8px 12px;
  border-top: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.08));
}
.am-q-manual-input {
  width: 100%;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.14));
  background: transparent;
  color: var(--cpq-text-primary);
  font-size: 12.5px;
  padding: 0 10px;
  outline: none;
}
.am-q-manual-input:focus {
  border-color: var(--cpq-accent-primary, #1677ff);
}
.am-q-manual-input::placeholder {
  color: var(--cpq-text-muted, #8c8c8c);
}
.am-q-foot {
  padding: 6px 12px;
  border-top: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.08));
  font-size: 11.5px;
  color: var(--cpq-text-muted, #8c8c8c);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
/* 已答卡：一行静态记录（问题 + 已选答案），不占聊天流 */
.am-q-done {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 4px 10px;
  border-radius: 10px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, .12));
  background: var(--cpq-overlay-w06, rgba(255, 255, 255, .06));
  font-size: 12px;
  line-height: 18px;
  color: var(--cpq-text-secondary, #a6adb4);
}
.am-q-done-check {
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #16a34a;
  border: 1px solid #16a34a55;
}
.am-q-done-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.am-q-done-answer {
  flex: none;
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--cpq-text-primary, inherit);
  font-weight: 600;
}
.am-q-form-hint {
  min-width: 0;
}
.am-q-submit {
  flex: none;
  padding: 4px 14px;
  border-radius: 8px;
  border: 1px solid var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-accent-primary, #1677ff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s ease;
}
.am-q-submit:disabled {
  opacity: .4;
  cursor: default;
}
.am-q-key {
  flex: none;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  border-radius: 6px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.14));
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--cpq-text-secondary, #a6adb4);
}
.am-q-opt:hover .am-q-key {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
.am-q-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.am-q-label {
  font-size: 13px;
  line-height: 1.4;
  color: var(--cpq-text-primary);
  word-break: break-word;
}
.am-q-desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--cpq-text-muted, #8c8c8c);
  word-break: break-word;
}

.am-bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 13px;
  line-height: 1.7;
  word-break: break-word;
  white-space: pre-wrap;
}

.role-user .am-bubble {
  background: var(--cpq-accent-primary, #1677ff);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.role-assistant .am-bubble,
.role-system .am-bubble {
  background: var(--cpq-overlay-w3);
  color: var(--cpq-text-primary);
  border: none;
  border-bottom-left-radius: 4px;
}

.am-cursor {
  display: inline-block;
  animation: am-blink 1s steps(2, start) infinite;
  color: var(--cpq-accent-primary, #1677ff);
  margin-left: 1px;
}

@keyframes am-blink {
  to { visibility: hidden; }
}

.am-status-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--cpq-text-secondary, #a6adb4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 正文已流出后挂载的状态行：换行到正文下方，留一点呼吸 */
.am-status-under {
  display: flex;
  margin-top: 6px;
}
.am-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677ff);
  animation: am-pulse-dot 1.1s ease-in-out infinite;
  flex: none;
}
@keyframes am-pulse-dot {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.1); }
}
.am-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
}

.am-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  animation: am-typing-bounce 1.2s infinite ease-in-out;
}

.am-typing i:nth-child(2) { animation-delay: 0.15s; }
.am-typing i:nth-child(3) { animation-delay: 0.3s; }

@keyframes am-typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
  30% { transform: translateY(-3px); opacity: 1; }
}
</style>
