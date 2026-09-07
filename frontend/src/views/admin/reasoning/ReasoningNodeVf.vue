<script setup lang="ts">
/** vue flow 自定义节点（注册名 rf）。复用 Glass Console 玻璃卡样式 + 左右 Handle。
 *  data 由 ReasoningFlowCanvas 注入：{ stepType, label, configurable }。
 *  元数据（中文名/职能/来源/图标）统一读 utils/reasoningNodeMeta（palette/节点卡/抽屉共用真源）。 */
import { computed, inject, ref, watch, nextTick, type Ref } from 'vue'
import { useNodeArtifact } from '@/composables/useNodeArtifact'
import { Handle, Position } from '@vue-flow/core'
import { reasoningNodeMeta, nodeArchetype } from '@/utils/reasoningNodeMeta'
import { PlayCircleOutlined } from '@ant-design/icons-vue'

const props = defineProps<{ id: string; data: any }>()
const stepType = computed(() => props.data?.stepType || '')
const runtime = computed(() => props.data?.runtime || stepType.value)
const instanceType = computed(() => runtime.value || stepType.value)
const instanceMeta = computed(() => reasoningNodeMeta(instanceType.value))
const archetypeMeta = computed(() => reasoningNodeMeta(nodeArchetype(instanceType.value)))
const meta = computed(() => instanceMeta.value || archetypeMeta.value)
const showName = computed(() => props.data?.label || instanceMeta.value?.name || archetypeMeta.value?.name || instanceType.value)
const typeLabel = computed(() => (archetypeMeta.value?.name || nodeArchetype(instanceType.value)).replace(/节点$/, '').trim())
const showTypeLabel = computed(() => Boolean(instanceMeta.value) && instanceType.value !== nodeArchetype(instanceType.value))
const isCondition = computed(() => runtime.value === 'condition')
const isInput = computed(() => stepType.value === 'input')
const isAgentFill = computed(() => runtime.value === 'agent_fill')
const { open: openArtifact } = useNodeArtifact()
const sharedReq = inject<Ref<string> | null>('studioReqText', null)
const studioRun = inject<(() => Promise<void>) | null>('studioRun', null)
const studioRunning = inject<Ref<boolean> | null>('studioRunning', null)
const studioEnableClarity = inject<Ref<boolean> | null>('studioEnableClarity', null)
const studioReqSlotsView = inject<Ref<Record<string, any> | null> | null>('studioReqSlotsView', null)
const fieldsEl = ref<HTMLElement | null>(null)
const followKey = ref('')

// 歌词式跟随滚动：运行时把最新「反问题」或「最新填充」字段滚入节点卡字段区视野。
watch(() => studioReqSlotsView?.value ?? null, (view) => {
  if (!view || !view.running) return
  const flat = (view.rows || []).flatMap((g: any) => (Array.isArray(g.fields) ? g.fields : []))
  const asked = flat.find((f: any) => f.status === 'asked')
  const key = asked?.key || [...flat].reverse().find((f: any) => f.status === 'filled')?.key
  if (key && key !== followKey.value) followKey.value = key
}, { deep: true })

watch(followKey, (key) => {
  if (!key) return
  nextTick(() => {
    fieldsEl.value?.querySelector(`[data-key="${key}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
})
const draftInput = computed({
  get: () => sharedReq?.value ?? (typeof props.data?.input === 'string' ? props.data.input : ''),
  set: (value: string) => {
    if (sharedReq) sharedReq.value = value
  },
})
const clarifyChecked = computed({
  get: () => studioEnableClarity?.value ?? true,
  set: (v: boolean) => { if (studioEnableClarity) studioEnableClarity.value = v },
})
const canRun = computed(() => !!studioRun && !!draftInput.value.trim() && !studioRunning?.value)
const runtimeInput = computed(() => props.data?.input)
const runtimeOutput = computed(() => props.data?.output)
const runtimeSummary = computed(() => props.data?.summary)
const runtimeArtifact = computed(() => props.data?.artifact)
function openRuntimeArtifact() {
  if (!runtimeArtifact.value) return
  openArtifact({
    kind: runtimeArtifact.value.kind,
    title: runtimeArtifact.value.title,
    data: runtimeArtifact.value.data,
    input: runtimeInput.value,
    output: runtimeOutput.value,
  })
}
function fmtVal(v: any): string {
  if (v == null) return ''
  if (typeof v === 'string') return v.length > 80 ? v.slice(0, 80) + '…' : v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return '[' + v.map(fmtVal).filter(Boolean).join(', ') + ']'
  if (typeof v === 'object') return JSON.stringify(v) || ''
  return String(v)
}
function statusText(s: string) {
  if (s === 'filled') return '已填'
  if (s === 'asked') return '缺 · 反问'
  return '未填 · 可选'
}
const FIELD_LABELS: Record<string, string> = {
  requirement_text: '需求原文', normalized_text: '规范化文本', opportunity_id: '商机ID',
  matches: '候选机型', reason: '推荐理由', trace: '推导链', count: '候选数',
  kp_by_model: '按机型配件', kp_parts: '配件清单', by_category: '按类别汇总', proposal: '配件建议',
  plans_count: '方案数', plan_names: '方案名', output_kind: '输出类型', target: '交接目标',
  slots: '登记字段', purchase_qty: '数量', missing_critical: '关键缺失', issues: '异常项', question: '反问题',
  baselines: '基准机型', result: '执行结果', plans: '候选方案',
}
function hasValue(v: any): boolean {
  if (v === null || v === undefined) return false
  if (typeof v === 'string') return v.trim() !== ''
  if (typeof v === 'number') return !Number.isNaN(v)
  if (Array.isArray(v)) return v.length > 0
  if (typeof v === 'object') return Object.keys(v).length > 0
  return Boolean(v)
}
function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key
}
// 运行时字段卡：需求理解节点用「线索登记表」，其余产出节点用「字段预览」，点「查看完整」弹完整文案。
const runtimeCard = computed(() => {
  if (isAgentFill.value) {
    const v = studioReqSlotsView?.value
    return v ? { ...v, title: '线索登记表', progressLabel: '已填' } : null
  }
  const art = runtimeArtifact.value
  if (art && (art.kind === 'l6_chassis' || art.kind === 'kp_table')) {
    const isKp = art.kind === 'kp_table'
    const rows = Array.isArray(art.data?.rows) ? art.data.rows : []
    const fields = rows.map((r: any, i: number) => {
      const name = isKp ? (r.catalogue || r.part_category || '') : (r.catalogue || '')
      const spec = isKp ? '' : (r.description || '')
      const qty = Number(r.qty || 1)
      const detail = [spec, qty > 1 ? `× ${qty}` : ''].filter(Boolean).join(' ')
      return { key: 'row' + i, label: name, value: detail || '1', status: r.unmatched ? 'asked' : 'filled' }
    })
    const unmatchedN = rows.filter((r: any) => r.unmatched).length
    return {
      cold: false,
      title: art.title || (isKp ? 'KP表' : '机箱表'),
      badgeText: rows.length ? '已生成' : '未生成',
      badgeClass: rows.length ? 'done' : 'idle',
      filled: rows.length,
      total: rows.length,
      pctText: rows.length ? '100%' : '0%',
      missingCount: unmatchedN,
      rows: [{ title: isKp ? '配件清单' : '机箱配置', fields }],
      showValue: true,
      progressLabel: '项',
    }
  }
  if (!runtimeArtifact.value) return null
  const out = runtimeOutput.value
  if (!out || typeof out !== 'object' || Array.isArray(out)) return null
  const entries = Object.entries(out).filter(([, v]) => hasValue(v))
  if (!entries.length) return null
  const fields = entries.map(([key, val]) => ({
    key,
    label: fieldLabel(key),
    value: fmtVal(val),
    status: 'filled',
  }))
  return {
    cold: false,
    title: meta.value?.name || showName.value || '节点产出',
    badgeText: '已生成',
    badgeClass: 'done',
    filled: fields.length,
    total: fields.length,
    pctText: '100%',
    missingCount: 0,
    rows: [{ title: '产出', fields }],
    showValue: true,
    progressLabel: '项',
  }
})

// 运行时字段卡是否展示：agent_fill 以「确有登记内容 / 节点已执行 / 有产物」为准，
// 与角色思考 busy（studio running 顶起 !cold）解耦，避免空卡显示「填充中」闪断。
const runtimeCardVisible = computed(() => {
  const rc = runtimeCard.value
  if (!rc) return false
  if (isAgentFill.value) {
    const v = studioReqSlotsView?.value
    return !!(v?.filled || v?.missingCount) || !!props.data?.execState || !!runtimeArtifact.value
  }
  return !rc.cold || !!props.data?.execState || !!runtimeArtifact.value
})
</script>

<template>
  <div class="rf-node-vf glass-light" :class="{
    'rf-node--cfg': data?.configurable,
    'rf-node--running': data?.execState === 'running',
    'rf-node--done': data?.execState === 'done',
    'rf-node--trace': data?.trace,
    'rf-node--dim': data?.dim,
  }">
    <Handle type="target" :position="Position.Left" class="rf-handle" />
    <div class="rf-head">
      <span class="rf-icon ni-chip" :class="`ni--${meta?.tone || 'gray'}`" v-if="meta?.icon">
        <component :is="meta.icon" />
      </span>
      <div class="rf-head-main">
        <div class="rf-title-row">
          <span class="rf-label">{{ showName }}</span>
          <span v-if="data?.badge" class="rf-badge">{{ data.badge }}</span>
        </div>
        <div class="rf-meta-row">
          <span v-if="showTypeLabel" class="rf-type">{{ typeLabel }}</span>
        <span v-if="meta?.fallback" class="rf-cfg-tag rf-tag--fallback" title="AI 失效时才走的兜底节点">兜底</span>
        <span v-if="data?.configurable" class="rf-cfg-tag">可配置</span>
        </div>
      </div>
    </div>
    <div v-if="meta?.desc" class="rf-desc">{{ meta.desc }}</div>
    <textarea
      v-if="isInput"
      v-model="draftInput"
      class="rf-input-edit nodrag"
      rows="3"
      placeholder="输入客户需求文本…"
      @mousedown.stop
      @click.stop
    />
    <div v-if="isInput" class="rf-node-run nodrag" @mousedown.stop @click.stop>
      <a-checkbox v-model:checked="clarifyChecked" size="small">允许反问</a-checkbox>
      <a-button type="primary" size="small" :loading="!!studioRunning" :disabled="!canRun" @click.stop="studioRun?.()">
        <template #icon><PlayCircleOutlined /></template>
        {{ studioRunning ? '运行中…' : '运行' }}
      </a-button>
    </div>
    <div v-if="runtimeOutput && !runtimeCard" class="rf-io-block rf-io-out">
      <div class="rf-io-title">→ 产出 · 下游交接</div>
      <div v-if="runtimeSummary" class="rf-summary-text">{{ runtimeSummary }}</div>
      <div class="rf-io-row"><span class="rf-io-k">值</span><span class="rf-io-v">{{ fmtVal(runtimeOutput) }}</span></div>
    </div>
    <div v-if="runtimeArtifact && !runtimeCard" class="rf-artifact-chip" title="点击查看结果" @click.stop="openRuntimeArtifact">{{ runtimeArtifact.title }}</div>
    <!-- 运行时字段卡：需求理解节点用「线索登记表」，其余产出节点用「字段预览」，点「查看完整」看完整内容 -->
    <div v-if="runtimeCard && runtimeCardVisible" class="rf-node-reg">
      <div class="nr-head">
        <span class="nr-name">{{ runtimeCard.title }}</span>
        <span class="nr-badge" :class="runtimeCard?.badgeClass">{{ runtimeCard?.badgeText }}</span>
      </div>
      <div class="nr-prog">
        <div class="nr-row"><span>{{ runtimeCard?.filled }} / {{ runtimeCard?.total }} {{ runtimeCard?.progressLabel || '已填' }}</span><span v-if="runtimeCard?.missingCount">{{ runtimeCard?.missingCount }} 关键缺失</span></div>
        <div class="nr-bar"><i :style="{ width: runtimeCard?.pctText }"></i></div>
      </div>
      <div v-if="runtimeCard.cold" class="nr-cold">暂无可展示的登记字段，等待模型理解需求…</div>
      <div ref="fieldsEl" class="nr-fields">
        <div v-for="group in runtimeCard?.rows || []" :key="group.title" class="rf-fg">
          <div class="rf-fg-title">{{ group.title }}</div>
          <div v-for="f in group.fields" :key="f.key" :data-key="f.key" class="rf-fld" :class="{ 'rf-fld--ask': f.status === 'asked' }">
            <span class="rf-fld-dot" :class="'rf-fld-dot--' + f.status"></span>
            <span class="rf-fld-lb">{{ f.label }}</span>
            <span v-if="runtimeCard.showValue && f.value != null" class="rf-fld-v" :title="f.value">{{ f.value }}</span>
            <span v-else class="rf-fld-st" :class="'rf-fld-st--' + f.status">{{ statusText(f.status) }}</span>
          </div>
        </div>
      </div>
      <div class="nr-foot">
        <span class="nr-dim">节点内滚动</span>
        <a v-if="runtimeArtifact" class="rf-art-view" @click.stop="openRuntimeArtifact">查看完整 →</a>
      </div>
    </div>
    <!-- condition 节点：双出口 Handle（真=true 上 / 假=false 下）；其余节点单出口 -->
    <!-- 智能对话填表 Agent 节点：入口左 / 出口右，单一主链，无反问回边 -->
    <template v-if="isCondition">
      <Handle id="true" type="source" :position="Position.Right" class="rf-handle rf-handle--branch" style="top: 28%;" />
      <Handle id="false" type="source" :position="Position.Right" class="rf-handle rf-handle--branch" style="top: 72%;" />
      <span class="rf-handle-label rf-handle-label--true">真</span>
      <span class="rf-handle-label rf-handle-label--false">假</span>
    </template>
    <Handle v-else type="source" :position="Position.Right" class="rf-handle" />
  </div>
</template>

<style scoped>
.rf-node-vf {
  width: 268px; padding: 10px 14px;
  border-radius: var(--cpq-radius-md, 12px);
  cursor: grab;
  position: relative;
}
.rf-node--cfg { border-color: var(--cpq-glass-border-strong) !important; }
.rf-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.rf-icon { width: 26px; height: 26px; font-size: 14px; border-radius: 7px; }
.rf-icon :deep(svg) { width: 15px; height: 15px; }
.rf-head-main { flex: 1; min-width: 0; }
.rf-title-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.rf-label {
  font-weight: 600; color: var(--cpq-text-primary); font-size: 14px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rf-meta-row { display: flex; align-items: center; gap: 5px; margin-top: 4px; min-width: 0; }
.rf-type {
  font-size: 11px; color: var(--cpq-text-secondary); white-space: nowrap;
}
.rf-cfg-tag {
  font-size: 10px; padding: 0 6px; border-radius: 6px;
  background: var(--cpq-overlay-w10); color: var(--cpq-accent-primary);
}
.rf-tag--fallback { background: rgba(250, 140, 22, 0.14); color: var(--cpq-accent-warning, #fa8c16); }
.rf-badge {
  font-size: 10px; padding: 0 6px; border-radius: 6px;
  background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary);
  font-weight: 600;
  flex-shrink: 0;
}
/* 试运行节点高亮：running 蓝边发光 / done 绿边 */
.rf-node--running {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 16px var(--cpq-overlay-a20);
}
.rf-node--done { border-color: var(--cpq-color-success) !important; }
/* 路径回溯：生成链节点高亮特写，其余变暗 */
.rf-node--trace { border-color: var(--cpq-accent-primary) !important; box-shadow: 0 0 20px var(--cpq-overlay-a20); }
.rf-node--dim { opacity: 0.3; }
.rf-desc {
  font-size: 12px; color: var(--cpq-text-secondary); margin-top: 7px; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.rf-input-edit {
  width: 100%; margin-top: 8px; padding: 7px 8px; resize: vertical;
  border-radius: 8px; border: 1px solid rgba(22,119,255,.28);
  background: rgba(22,119,255,.05); color: var(--cpq-text-primary);
  font-size: 12px; line-height: 1.5; box-sizing: border-box;
}
.rf-input-edit::placeholder { color: var(--cpq-text-muted); }
.rf-input-edit:focus { outline: none; border-color: var(--cpq-accent-primary, #1677FF); }
.rf-node-run { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }
.rf-node-run .ant-checkbox-wrapper { font-size: 11px; color: var(--cpq-text-secondary); }
.rf-node-ask-opts { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.rf-node-ask-opt {
  font-size: 11px; line-height: 1.5; padding: 2px 8px; border-radius: 999px; cursor: pointer;
  color: var(--cpq-accent-warning, #fa8c16); background: rgba(250, 173, 20, 0.12);
  border: 1px solid rgba(250, 173, 20, 0.3);
}
.rf-node-ask-opt:hover { background: rgba(250, 173, 20, 0.2); }
.rf-node-ask-reply { display: flex; gap: 6px; margin-top: 8px; }
.rf-node-ask-input {
  flex: 1; min-width: 0; padding: 5px 8px; font-size: 11px; border-radius: 8px;
  border: 1px solid rgba(250,173,20,.35); background: var(--cpq-overlay-w4);
  color: var(--cpq-text-primary); box-sizing: border-box;
}
.rf-node-ask-input::placeholder { color: var(--cpq-text-muted); }
.rf-node-ask-btn {
  flex: none; padding: 4px 10px; font-size: 11px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--cpq-accent-warning, #fa8c16); color: var(--cpq-accent-warning, #fa8c16);
  background: transparent;
}
.rf-node-ask-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.rf-io-block { margin-top: 8px; padding: 7px 8px; border-radius: 8px; background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.06); }
.rf-io-block.rf-io-in { border-color: rgba(22,119,255,.22); }
.rf-io-block.rf-io-summary { border-color: rgba(250,140,22,.22); background: rgba(250,140,22,.05); }
.rf-io-block.rf-io-out { border-color: rgba(82,201,160,.24); }
.rf-io-block.rf-ask { border-color: rgba(250,173,20,.28); background: rgba(250,173,20,.06); }
.rf-io-title { font-size: 10px; color: var(--cpq-text-muted); margin-bottom: 4px; font-weight: 600; }
.rf-summary-text { font-size: 11px; color: var(--cpq-text-primary); line-height: 1.5; }
.rf-ask-text { font-size: 11px; color: var(--cpq-accent-warning, #fa8c16); line-height: 1.5; }
.rf-io-row { display: flex; justify-content: space-between; gap: 6px; font-size: 10px; margin-top: 3px; }
.rf-io-k { color: var(--cpq-text-secondary); flex: none; }
.rf-io-v { color: var(--cpq-text-primary); text-align: right; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rf-artifact-chip {
  margin-top: 8px; display: inline-flex; align-items: center; gap: 5px; cursor: pointer;
  font-size: 10px; padding: 3px 8px; border-radius: 999px; color: #9ec5ff;
  background: var(--cpq-overlay-a10); border: 1px solid rgba(22,119,255,.18);
}
/* 需求理解节点内嵌「线索登记表」进度卡（节点内滚动） */
.rf-node-reg { margin-top: 8px; padding: 8px 9px; border-radius: 8px; background: rgba(255,255,255,.035); border: 1px solid rgba(22,119,255,.2); }
.rf-node-reg .nr-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.rf-node-reg .nr-name { font-size: 11px; font-weight: 600; color: var(--cpq-text-primary); }
.rf-node-reg .nr-badge { font-size: 9px; padding: 1px 6px; border-radius: 999px; flex-shrink: 0; }
.rf-node-reg .nr-badge.done { background: var(--cpq-overlay-success15); color: var(--cpq-color-success); }
.rf-node-reg .nr-badge.fill { background: rgba(250,173,20,.14); color: var(--cpq-accent-warning, #fa8c16); }
.rf-node-reg .nr-badge.idle { background: var(--cpq-overlay-w8); color: var(--cpq-text-muted); }
.rf-node-reg .nr-prog { margin-top: 6px; }
.rf-node-reg .nr-cold { margin-top: 6px; font-size: 11px; color: var(--cpq-text-muted); }
.rf-node-reg .nr-row { display: flex; justify-content: space-between; gap: 6px; font-size: 9px; color: var(--cpq-text-secondary); }
.rf-node-reg .nr-bar { margin-top: 4px; height: 4px; border-radius: 999px; background: var(--cpq-overlay-w10); overflow: hidden; }
.rf-node-reg .nr-bar i { display: block; height: 100%; border-radius: 999px; background: var(--cpq-accent-primary); transition: width .3s; }
.rf-node-reg .nr-fields { margin-top: 6px; max-height: 118px; overflow-y: auto; padding-right: 2px; scrollbar-width: thin; }
.rf-node-reg .rf-fg { margin-top: 4px; }
.rf-node-reg .rf-fg:first-child { margin-top: 0; }
.rf-node-reg .rf-fg-title { font-size: 9px; color: var(--cpq-text-muted); font-weight: 600; margin-bottom: 2px; }
.rf-node-reg .rf-fld { display: flex; align-items: center; gap: 4px; font-size: 9px; line-height: 1.7; }
.rf-node-reg .rf-fld-dot { width: 5px; height: 5px; border-radius: 999px; flex-shrink: 0; }
.rf-node-reg .rf-fld-dot--filled { background: var(--cpq-color-success); }
.rf-node-reg .rf-fld-dot--asked { background: var(--cpq-accent-warning, #fa8c16); }
.rf-node-reg .rf-fld-dot--optional { background: var(--cpq-text-muted); }
.rf-node-reg .rf-fld-lb { flex: 1; min-width: 0; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rf-node-reg .rf-fld-st { flex-shrink: 0; font-size: 8px; }
.rf-node-reg .rf-fld-st--filled { color: var(--cpq-color-success); }
.rf-node-reg .rf-fld-st--asked { color: var(--cpq-accent-warning, #fa8c16); }
.rf-node-reg .rf-fld-st--optional { color: var(--cpq-text-muted); }
.rf-node-reg .rf-fld-v { flex: 1; min-width: 0; margin-left: 4px; color: var(--cpq-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: right; font-size: 9px; }
.rf-node-reg .nr-foot { margin-top: 6px; display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.rf-node-reg .nr-dim { font-size: 9px; color: var(--cpq-text-muted); }
.rf-node-reg .rf-art-view { font-size: 9px; color: #9ec5ff; cursor: pointer; }
.rf-handle {
  width: 10px !important; height: 10px !important;
  background: var(--cpq-accent-primary, #1677FF) !important;
  border: 2px solid var(--cpq-glass-3-bg, #fff) !important;
}

/* 节点图标软底色块（与 palette 共用同一套 ni-- 色调） */
.ni-chip {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: var(--cpq-radius-sm, 8px);
  font-size: 15px; flex-shrink: 0;
}
.ni-chip.ni--blue { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.ni-chip.ni--purple { background: rgba(168, 85, 247, 0.12); color: var(--cpq-color-purple, #a855f7); }
.ni-chip.ni--green { background: var(--cpq-overlay-success15); color: var(--cpq-color-success, #52C9A0); }
.ni-chip.ni--orange { background: rgba(250, 140, 22, 0.12); color: var(--cpq-color-orange, #fa8c16); }
.ni-chip.ni--cyan { background: var(--cpq-overlay-cyan15); color: var(--cpq-accent-cyan, #36CFCF); }
.ni-chip.ni--gray { background: var(--cpq-overlay-w8); color: var(--cpq-text-muted); }
/* condition 双出口标签（真/假分支） */
.rf-handle-label { position: absolute; right: 18px; font-size: 9px; line-height: 1; pointer-events: none; }
.rf-handle-label--true { top: 25%; color: var(--cpq-color-success); }
.rf-handle-label--false { top: 69%; color: var(--cpq-accent-warning, #fa8c16); }
</style>
