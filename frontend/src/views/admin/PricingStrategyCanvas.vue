<script setup lang="ts">
/** 报价策略画布 — pricing 域专用视图（替换 Strategies.vue 的通用 a-table）。
 *  左栏：报价场景（pricing_scenario，业务说明 + 匹配条件 scope）
 *  右栏：毛利三档规则（margin_tier，被场景连线引用）
 *  中间：SVG 贝塞尔连线（场景.body.rule_id → 规则.id）
 *  signature：场景→规则 的可视化连线，体现"场景命中 → 取连线规则"的匹配语义。
 *  CRUD 走 /api/strategies；改完 invalidatePricingRules 让报价工作台读到新连线。 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { strategyApi, type Strategy } from '@/api/strategies'
import { usePricingRulesStore } from '@/stores/pricingRules'

const emit = defineEmits<{ changed: [] }>()

const pricingRulesStore = usePricingRulesStore()

const PLATFORMS = ['Polaris', 'Orion', 'Intel', '工作站']
const CUSTOMER_TYPES = ['直销', '渠道', '集成商', '最终用户', '代理商']
const MARGIN_MAX = 25

const scenarios = ref<Strategy[]>([])   // pricing_scenario
const rules = ref<Strategy[]>([])        // margin_tier
const loading = ref(false)

const canvasRef = ref<HTMLElement | null>(null)
const scenarioRefs = ref<Record<number, HTMLElement | null>>({})
const ruleRefs = ref<Record<number, HTMLElement | null>>({})
const lines = ref<{ id: string; sx: number; sy: number; ex: number; ey: number }[]>([])

async function load() {
  loading.value = true
  try {
    const [sc, rl] = await Promise.all([
      strategyApi.list({ domain: 'pricing', status: 'active', type: 'pricing_scenario' }),
      strategyApi.list({ domain: 'pricing', status: 'active', type: 'margin_tier' }),
    ])
    scenarios.value = sc.strategies || []
    rules.value = rl.strategies || []
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
    await nextTick()
    recompute()
  }
}

function anchorPos(el: HTMLElement | null, side: 'right' | 'left') {
  if (!el || !canvasRef.value) return null
  const c = canvasRef.value.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  if (!r.width) return null
  const x = side === 'right' ? r.right - c.left : r.left - c.left
  const y = r.top + r.height / 2 - c.top
  return { x, y }
}

function recompute() {
  const out: typeof lines.value = []
  for (const s of scenarios.value) {
    const rid = s.body?.rule_id
    if (rid == null) continue
    const sp = anchorPos(scenarioRefs.value[s.id], 'right')
    const ep = anchorPos(ruleRefs.value[rid], 'left')
    if (!sp || !ep) continue
    out.push({ id: `${s.id}-${rid}`, sx: sp.x, sy: sp.y, ex: ep.x, ey: ep.y })
  }
  lines.value = out
}

function pathFor(l: { sx: number; sy: number; ex: number; ey: number }) {
  const dx = Math.max(40, Math.abs(l.ex - l.sx) / 2)
  return `M ${l.sx},${l.sy} C ${l.sx + dx},${l.sy} ${l.ex - dx},${l.ey} ${l.ex},${l.ey}`
}

const ruleLinkCount = computed<Record<number, number>>(() => {
  const m: Record<number, number> = {}
  for (const s of scenarios.value) {
    const rid = s.body?.rule_id
    if (rid != null) m[rid] = (m[rid] || 0) + 1
  }
  return m
})

function scopeTags(s: Strategy) {
  const out: string[] = []
  if (s.scope?.platform_type) out.push(`平台·${s.scope.platform_type}`)
  if (s.scope?.customer_type) out.push(`客户·${s.scope.customer_type}`)
  return out
}
function tierGradient(b: any) {
  const pct = (v: number) => Math.min(Math.max(v / MARGIN_MAX * 100, 0), 100)
  const f = pct(b?.floor || 0), s = pct(b?.standard || 0), p = pct(Math.min(b?.premium || 0, MARGIN_MAX))
  return `linear-gradient(to right,
    var(--cpq-accent-warning,#fa8c16) 0%, var(--cpq-accent-warning,#fa8c16) ${f}%,
    var(--cpq-accent-primary,#1677ff) ${f}%, var(--cpq-accent-primary,#1677ff) ${s}%,
    var(--cpq-accent-success,#52c41a) ${s}%, var(--cpq-accent-success,#52c41a) ${p}%,
    #389e0d ${p}%, #389e0d 100%)`
}
function linkedRuleName(s: Strategy) {
  const rid = s.body?.rule_id
  if (rid == null) return ''
  return rules.value.find(r => r.id === rid)?.name || '(规则已删)'
}

let ro: ResizeObserver | null = null
onMounted(async () => {
  await load()
  ro = new ResizeObserver(() => recompute())
  if (canvasRef.value) ro.observe(canvasRef.value)
  window.addEventListener('resize', recompute)
  window.addEventListener('mousemove', onWindowMove)
  window.addEventListener('mouseup', onWindowUp)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  window.removeEventListener('resize', recompute)
  window.removeEventListener('mousemove', onWindowMove)
  window.removeEventListener('mouseup', onWindowUp)
})

// ── 场景 CRUD ──
const scModalVisible = ref(false)
const scEditing = ref<Strategy | null>(null)
const scForm = ref<any>({})
function openScNew() {
  scEditing.value = null
  scForm.value = { name: '', description: '', platform: '', customer: '' }
  scModalVisible.value = true
}
function openScEdit(s: Strategy) {
  scEditing.value = s
  scForm.value = {
    name: s.name,
    description: s.body?.description || s.description || '',
    platform: s.scope?.platform_type || '',
    customer: s.scope?.customer_type || '',
  }
  scModalVisible.value = true
}
async function saveSc() {
  const f = scForm.value
  if (!f.name?.trim()) { message.warning('请填场景名称'); return }
  const scope: any = {}
  if (f.platform) scope.platform_type = f.platform
  if (f.customer) scope.customer_type = f.customer
  const body: any = { description: f.description || '' }
  if (scEditing.value && scEditing.value.body?.rule_id != null) body.rule_id = scEditing.value.body.rule_id
  const payload = {
    domain: 'pricing' as const, type: 'pricing_scenario', name: f.name.trim(),
    description: f.description || '', scope, body, status: 'active' as const,
  }
  try {
    if (scEditing.value) await strategyApi.update(scEditing.value.id, payload)
    else await strategyApi.create(payload)
    message.success(scEditing.value ? '已保存' : '已新建场景')
    scModalVisible.value = false
    await reloadAll()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}
function removeSc(s: Strategy) {
  Modal.confirm({
    title: '删除场景', content: `确定删除「${s.name}」？连线会一并断开。`,
    okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      await strategyApi.delete(s.id)
      message.success('已删除')
      await reloadAll()
    },
  })
}

// ── 规则 CRUD ──
const rlModalVisible = ref(false)
const rlEditing = ref<Strategy | null>(null)
const rlForm = ref<any>({})
function openRlNew() {
  rlEditing.value = null
  rlForm.value = { name: '', description: '', floor: 8, standard: 12, premium: 18 }
  rlModalVisible.value = true
}
function openRlEdit(r: Strategy) {
  rlEditing.value = r
  rlForm.value = {
    name: r.name, description: r.description || '',
    floor: r.body?.floor ?? 8, standard: r.body?.standard ?? 12, premium: r.body?.premium ?? 18,
  }
  rlModalVisible.value = true
}
async function saveRl() {
  const f = rlForm.value
  if (!f.name?.trim()) { message.warning('请填规则名称'); return }
  const body = { floor: +f.floor, standard: +f.standard, premium: +f.premium }
  if (!(body.floor < body.standard && body.standard < body.premium)) {
    message.warning('三档需满足：底线 < 标准 < 优质'); return
  }
  const payload = {
    domain: 'pricing' as const, type: 'margin_tier', name: f.name.trim(),
    description: f.description || '', scope: null, body, status: 'active' as const,
  }
  try {
    if (rlEditing.value) await strategyApi.update(rlEditing.value.id, payload)
    else await strategyApi.create(payload)
    message.success(rlEditing.value ? '已保存' : '已新建规则')
    rlModalVisible.value = false
    await reloadAll()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}
function removeRl(r: Strategy) {
  const linked = scenarios.value.filter(s => s.body?.rule_id === r.id).length
  Modal.confirm({
    title: '删除规则', content: linked ? `「${r.name}」被 ${linked} 个场景连线，删除后这些场景将断开。确定？` : `确定删除「${r.name}」？`,
    okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      await strategyApi.delete(r.id)
      message.success('已删除')
      await reloadAll()
    },
  })
}

async function reloadAll() {
  await load()
  pricingRulesStore.invalidatePricingRules()
  pricingRulesStore.ensurePricingRules()
  emit('changed')
}

// ── 拖拽连线：场景右锚点 → 规则卡（update body.rule_id；拖到空白处断开）──
const dragging = ref<{ scenarioId: number } | null>(null)
const tempLine = ref<{ sx: number; sy: number; ex: number; ey: number } | null>(null)
const dragOverRuleId = ref<number | null>(null)

function onScAnchorDown(e: MouseEvent, s: Strategy) {
  e.preventDefault()
  const sp = anchorPos(scenarioRefs.value[s.id], 'right')
  if (!sp) return
  dragging.value = { scenarioId: s.id }
  tempLine.value = { sx: sp.x, sy: sp.y, ex: sp.x, ey: sp.y }
}
function onWindowMove(e: MouseEvent) {
  if (!dragging.value || !canvasRef.value) return
  const c = canvasRef.value.getBoundingClientRect()
  tempLine.value = { ...tempLine.value!, ex: e.clientX - c.left, ey: e.clientY - c.top }
  let hit: number | null = null
  for (const r of rules.value) {
    const el = ruleRefs.value[r.id]
    if (!el) continue
    const rr = el.getBoundingClientRect()
    if (e.clientX >= rr.left && e.clientX <= rr.right && e.clientY >= rr.top && e.clientY <= rr.bottom) {
      hit = r.id; break
    }
  }
  dragOverRuleId.value = hit
}
async function onWindowUp() {
  const d = dragging.value
  const hit = dragOverRuleId.value
  dragging.value = null
  tempLine.value = null
  dragOverRuleId.value = null
  if (!d) return
  const s = scenarios.value.find(x => x.id === d.scenarioId)
  if (!s || s.body?.rule_id === hit) return
  const newBody = { ...(s.body || {}), rule_id: hit }
  try {
    await strategyApi.update(s.id, { body: newBody })
    message.success(hit ? '已连线' : '已断开')
    await reloadAll()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '连线失败')
  }
}
</script>

<template>
  <div class="ps-canvas">
    <div class="ps-toolbar">
      <span class="ps-tip">商机按平台/客户/场景命中左侧场景 → 取连线到的右侧毛利三档规则；连线拖拽编辑（task #10 待接入）。</span>
    </div>

    <a-spin :spinning="loading">
      <div class="ps-stage" ref="canvasRef">
        <!-- 左：场景 -->
        <div class="ps-col ps-col-left">
          <div class="ps-col-head">
            <span class="ps-col-title">报价场景</span>
            <a-button size="small" type="primary" ghost @click="openScNew">+ 场景</a-button>
          </div>
          <div class="ps-col-body">
            <div v-for="s in scenarios" :key="s.id"
                 :ref="el => { scenarioRefs[s.id] = el as HTMLElement | null }"
                 class="ps-card ps-scenario glass-light">
              <div class="ps-card-row">
                <span class="ps-card-name">{{ s.name }}</span>
                <span class="ps-card-ops">
                  <a-button size="small" link @click="openScEdit(s)">编辑</a-button>
                  <a-button size="small" link danger @click="removeSc(s)">删</a-button>
                </span>
              </div>
              <div class="ps-card-desc">{{ s.body?.description || s.description || '（无说明）' }}</div>
              <div class="ps-tags">
                <span v-for="t in scopeTags(s)" :key="t" class="ps-tag">{{ t }}</span>
                <span v-if="!scopeTags(s).length" class="ps-tag ps-tag-muted">通用兜底</span>
              </div>
              <div class="ps-link-info">
                <span v-if="s.body?.rule_id != null" class="ps-linked">→ {{ linkedRuleName(s) }}</span>
                <span v-else class="ps-unlinked">未连线（拖到右侧规则）</span>
              </div>
              <span class="ps-anchor ps-anchor-right" :class="{ linked: s.body?.rule_id != null }"
                    @mousedown="onScAnchorDown($event, s)" title="拖到右侧规则连线"></span>
            </div>
            <div v-if="!scenarios.length && !loading" class="ps-empty">暂无场景，点「+ 场景」新建</div>
          </div>
        </div>

        <!-- 中：连线层 -->
        <svg class="ps-lines">
          <defs>
            <marker id="ps-arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" fill="#1677ff" />
            </marker>
          </defs>
          <path v-for="l in lines" :key="l.id" :d="pathFor(l)" class="ps-line" marker-end="url(#ps-arrow)" />
          <path v-if="tempLine" :d="pathFor(tempLine)" class="ps-line ps-line-temp" />
        </svg>

        <!-- 右：规则 -->
        <div class="ps-col ps-col-right">
          <div class="ps-col-head">
            <span class="ps-col-title">毛利三档规则</span>
            <a-button size="small" type="primary" ghost @click="openRlNew">+ 规则</a-button>
          </div>
          <div class="ps-col-body">
            <div v-for="r in rules" :key="r.id"
                 :ref="el => { ruleRefs[r.id] = el as HTMLElement | null }"
                 class="ps-card ps-rule glass-light" :class="{ 'ps-drop-target': dragOverRuleId === r.id }">
              <div class="ps-card-row">
                <span class="ps-card-name">
                  {{ r.name }}
                  <span v-if="ruleLinkCount[r.id]" class="ps-link-count">×{{ ruleLinkCount[r.id] }}</span>
                </span>
                <span class="ps-card-ops">
                  <a-button size="small" link @click="openRlEdit(r)">编辑</a-button>
                  <a-button size="small" link danger @click="removeRl(r)">删</a-button>
                </span>
              </div>
              <div class="ps-tier-bar" :style="{ background: tierGradient(r.body) }"></div>
              <div class="ps-tier-vals">
                <span class="ps-tier-floor">底线 {{ r.body?.floor }}%</span>
                <span class="ps-tier-standard">标准 {{ r.body?.standard }}%</span>
                <span class="ps-tier-premium">优质 {{ r.body?.premium }}%</span>
              </div>
              <span class="ps-anchor ps-anchor-left" :class="{ linked: ruleLinkCount[r.id] }"></span>
            </div>
            <div v-if="!rules.length && !loading" class="ps-empty">暂无规则，点「+ 规则」新建</div>
          </div>
        </div>
      </div>
    </a-spin>

    <!-- 场景编辑 modal -->
    <a-modal v-model:open="scModalVisible" :title="scEditing ? '编辑场景' : '新建场景'" width="560px"
             ok-text="保存" :confirm-loading="false" @ok="saveSc">
      <a-form layout="vertical">
        <a-form-item label="场景名称"><a-input v-model:value="scForm.name" placeholder="如：渠道·竞标·Polaris" /></a-form-item>
        <a-form-item label="业务说明（命中此场景的业务含义）">
          <a-textarea v-model:value="scForm.description" :rows="2" placeholder="如：渠道商参与竞标，毛利让利一档" />
        </a-form-item>
        <a-form-item label="匹配条件（留空 = 不限；全留空 = 通用兜底）">
          <div class="ps-form-scope">
            <a-select v-model:value="scForm.platform" allow-clear placeholder="平台类型" style="width:100%">
              <a-select-option v-for="p in PLATFORMS" :key="p" :value="p">{{ p }}</a-select-option>
            </a-select>
            <a-select v-model:value="scForm.customer" allow-clear placeholder="客户类型" style="width:100%">
              <a-select-option v-for="c in CUSTOMER_TYPES" :key="c" :value="c">{{ c }}</a-select-option>
            </a-select>
          </div>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 规则编辑 modal -->
    <a-modal v-model:open="rlModalVisible" :title="rlEditing ? '编辑规则' : '新建规则'" width="480px"
             ok-text="保存" :confirm-loading="false" @ok="saveRl">
      <a-form layout="vertical">
        <a-form-item label="规则名称"><a-input v-model:value="rlForm.name" placeholder="如：标准三档 8/12/18" /></a-form-item>
        <a-form-item label="说明"><a-input v-model:value="rlForm.description" placeholder="（可选）规则依据" /></a-form-item>
        <div class="ps-form-tier">
          <a-form-item label="底线（百分点）"><a-input-number v-model:value="rlForm.floor" :min="0" :max="50" style="width:100%" /></a-form-item>
          <a-form-item label="标准（百分点）"><a-input-number v-model:value="rlForm.standard" :min="0" :max="50" style="width:100%" /></a-form-item>
          <a-form-item label="优质（百分点）"><a-input-number v-model:value="rlForm.premium" :min="0" :max="50" style="width:100%" /></a-form-item>
        </div>
        <p class="ps-form-hint">底线 &lt; 标准 &lt; 优质；底线用于报价利润率告警。</p>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.ps-canvas { display: flex; flex-direction: column; gap: 10px; }
.ps-toolbar { padding: 0 2px; }
.ps-tip { font-size: 12px; color: var(--cpq-text-muted); }

.ps-stage {
  position: relative;
  display: flex;
  gap: 120px;
  min-height: 320px;
  padding: 12px 8px;
}
.ps-col { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.ps-col-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 4px 10px;
  border-bottom: 1px solid var(--cpq-glass-border);
  margin-bottom: 10px;
}
.ps-col-title { font-weight: 600; color: var(--cpq-text-primary); }
.ps-col-body { display: flex; flex-direction: column; gap: 12px; }

/* 卡片：玻璃外观交 .glass-light 工具类（主题感知），scoped 只管布局 */
.ps-card {
  position: relative;
  padding: 12px 14px;
  border-radius: var(--cpq-radius-lg);
}
.ps-card-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ps-card-name { font-weight: 600; color: var(--cpq-text-primary); }
.ps-card-ops { white-space: nowrap; }
.ps-card-desc { font-size: 12px; color: var(--cpq-text-secondary); margin-top: 4px; line-height: 1.5; }
.ps-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.ps-tag {
  font-size: 11px; padding: 1px 7px; border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-overlay-w8);
  color: var(--cpq-accent-primary);
}
.ps-tag-muted { background: var(--cpq-overlay-w6); color: var(--cpq-text-muted); }
.ps-link-info { margin-top: 8px; font-size: 12px; }
.ps-linked { color: var(--cpq-accent-success); font-weight: 500; }
.ps-unlinked { color: var(--cpq-text-muted); }

.ps-link-count {
  font-size: 11px; margin-left: 6px; padding: 0 6px; border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-overlay-w10);
  color: var(--cpq-accent-success); font-weight: 500;
}
.ps-tier-bar { height: 8px; border-radius: 4px; margin-top: 8px; }
.ps-tier-vals { display: flex; gap: 12px; margin-top: 6px; font-size: 11px; font-variant-numeric: tabular-nums; }
.ps-tier-floor { color: var(--cpq-accent-warning); }
.ps-tier-standard { color: var(--cpq-accent-primary); }
.ps-tier-premium { color: var(--cpq-accent-success); }

.ps-empty {
  padding: 24px; text-align: center; font-size: 13px;
  color: var(--cpq-text-muted);
  border: 1px dashed var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md, 12px);
}

/* 连线锚点：LED 圆点，未连线灰边、已连线 accent 实心 */
.ps-anchor {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 12px; height: 12px; border-radius: 50%;
  background: #fff;
  border: 2px solid var(--cpq-text-muted);
  z-index: 2;
}
.ps-anchor.linked {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-primary);
}
.ps-anchor-right { right: -7px; cursor: crosshair; }
.ps-anchor-left { left: -7px; }

/* 拖拽命中高亮：蓝边环（复用 glass border-strong + 蓝光 overlay）*/
.ps-rule.ps-drop-target {
  border-color: var(--cpq-glass-border-strong) !important;
  box-shadow: 0 0 0 3px var(--cpq-overlay-a15, rgba(22,119,255,0.25)) !important;
}

/* SVG 连线层 */
.ps-lines {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: none; z-index: 1;
}
.ps-line {
  fill: none; stroke: var(--cpq-accent-primary, #1677FF); stroke-width: 2; opacity: 0.65;
}
.ps-line-temp { stroke-dasharray: 5 3; opacity: 0.85; }

.ps-form-scope { display: flex; flex-direction: column; gap: 8px; }
.ps-form-tier { display: flex; gap: 12px; }
.ps-form-tier > * { flex: 1; }
.ps-form-hint { font-size: 12px; color: var(--cpq-text-muted); margin-top: 4px; }
</style>
