<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { confirmWithReason } from './confirmWithReason'
import RecordTable from '@/components/opportunity/RecordTable.vue'
import SchemeEditor from '@/components/opportunity/SchemeEditor.vue'
import RequirementForm from '@/components/flow/RequirementForm.vue'
import { portalApi, type BomScheme, type FlowCard, type PortalBoard, type PortalSheetConfig, type RequirementSlots } from '@/api/portal'
import AssigneePickerModal from '@/components/opportunity/AssigneePickerModal.vue'
import { useDownstreamAssignee, ASSIGNEE_REQUIRED_DETAIL } from '@/composables/useDownstreamAssignee'

const props = defineProps<{
  board: PortalBoard
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'card-updated', card: FlowCard): void
}>()

const oppId = computed(() => props.board.opportunity?.opportunity_id || '')
const schemes = computed(() => props.board.bom_schemes || [])
const editable = computed(() => !props.readonly)
const requirements = computed(() => props.board.requirements || [])
const requirement = computed(() => props.board.requirement || props.board.requirements?.find((r) => r.status === 'current') || null)

// 编辑方案弹窗左侧的需求单只读参考：与上游需求单共用 RequirementForm（含多配置 tab），
// 打开弹窗时从 current 需求单回填；组件异步挂载晚于回填时由 reqRef watch 补灌。
interface RequirementFormExpose {
  toSlots(): RequirementSlots
  fromSlots(slots: RequirementSlots): void
  hasAnyPart: boolean
}
const reqRef = ref<RequirementFormExpose | null>(null)
const reqText = ref('')
let pendingReqSlots: RequirementSlots | null = null
function flushPendingReqSlots() {
  const pending = pendingReqSlots
  if (!reqRef.value || !pending) return
  reqRef.value.fromSlots(pending)
  pendingReqSlots = null
}
watch(reqRef, (form) => {
  if (form && pendingReqSlots) flushPendingReqSlots()
})
const flowCards = computed(() => props.board.flow_cards || [])
const {
  pickerOpen, pickerTitle, pickerOptions, pickerChosen,
  promptAssignee, confirmPicker, cancelPicker,
} = useDownstreamAssignee()

function cardFor(type: FlowCard['entities'][number]['entity_type'], entityId: number | string | null | undefined): FlowCard | undefined {
  if (entityId === null || entityId === undefined || entityId === '') return undefined
  return flowCards.value.find((card) => card.entities.some((e) => e.entity_type === type && e.entity_id === String(entityId)))
}

const requirementCardId = computed(() => cardFor('requirement', requirement.value?.version)?.id || null)

const pendingRequirements = computed(() =>
  requirements.value.filter((req) => {
    const card = cardFor('requirement', req.version)
    return card?.current_node === 'boming' && ['submitted', 'processing'].includes(card.flow_status)
  }),
)

function schemeForRequirement(req: { version: number }): BomScheme | null {
  const card = cardFor('requirement', req.version)
  const link = card?.entities.find((e) => e.entity_type === 'bom')
  return schemes.value.find((scheme) => String(scheme.id) === link?.entity_id) || null
}

function openSchemeForRequirement(req: { version: number }) {
  const scheme = schemeForRequirement(req)
  if (scheme) openScheme(scheme)
  else openNewForRequirement(req)
}

function editorFlowCardId() {
  const existing = cardFor('bom', editorSchemeId.value)
  return existing?.id ?? editorSourceRequirementId.value ?? requirementCardId.value
}

const editorOpen = ref(false)
// 弹窗打开时灌入 current 需求单快照（左侧只读参考）
watch(editorOpen, (open) => {
  if (!open) return
  pendingReqSlots = requirement.value?.slots || {}
  reqText.value = requirement.value?.requirement_text || ''
  nextTick(flushPendingReqSlots)
})
const editorSchemeId = ref<number | null>(null)
const editorUpdatedAt = ref('')
const editorSourceRequirementId = ref<number | null>(null)
const editorName = ref('')
const editorConfigs = ref<PortalSheetConfig[]>([])
const editorConfigRelation = ref<'compose' | 'alternative'>('compose')
const editorPrimaryConfig = ref('')
const editorReadonly = ref(false)
const editorRef = ref<InstanceType<typeof SchemeEditor> | null>(null)
const saving = ref(false)

const DEFAULT_KP_CATEGORIES = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC']

function blankConfig(name: string): PortalSheetConfig {
  return {
    name,
    server_model: '',
    description: '',
    qty: 1,
    l6_cost: 0,
    l6_margin: 0,
    l6_rows: [],
    kp_rows: DEFAULT_KP_CATEGORIES.map((part_category) => ({
      category: 'Key Parts',
      part_category,
      catalogue: '',
      description: '',
      qty: 1,
      base_price: 0,
      final_price: 0,
      profit_margin: 10,
      currency: 'RMB',
      note: '',
    })),
    totals: {},
  }
}

function cloneConfigs(configs: PortalSheetConfig[]) {
  return JSON.parse(JSON.stringify(configs || [])) as PortalSheetConfig[]
}

function inheritRequirementRelation(req?: { version: number }) {
  const r = requirements.value.find((item) => item.version === req?.version)
  const slots = (r || requirement.value)?.slots || {}
  editorConfigRelation.value = slots.config_relation === 'alternative' ? 'alternative' : 'compose'
  editorPrimaryConfig.value = slots.primary_config || ''
  if (editorConfigRelation.value === 'alternative' && !editorPrimaryConfig.value) {
    editorPrimaryConfig.value = editorConfigs.value[0]?.name || ''
  }
}

function openNew() {
  if (!editable.value) return
  editorSchemeId.value = null
  editorUpdatedAt.value = ''
  editorSourceRequirementId.value = null
  editorName.value = ''
  editorConfigs.value = [blankConfig('CFG1')]
  editorReadonly.value = false
  // 新建方案：从当前需求单继承「组合拆分/方案备选」模式（只拷贝，不回写需求单）
  inheritRequirementRelation()
  editorOpen.value = true
}

// 卡头的「新建方案」按钮在 OpportunityProcessBoard 的节点卡头上，经 expose 远调
defineExpose({ openNew })

function openNewForRequirement(req: { version: number }) {
  if (!editable.value) return
  editorSchemeId.value = null
  editorUpdatedAt.value = ''
  editorSourceRequirementId.value = cardFor('requirement', req.version)?.id || null
  editorName.value = ''
  editorConfigs.value = [blankConfig('CFG1')]
  editorReadonly.value = false
  inheritRequirementRelation(req)
  editorOpen.value = true
}

function openScheme(scheme: BomScheme) {
  editorSchemeId.value = scheme.id
  editorUpdatedAt.value = scheme.updated_at || ''
  editorSourceRequirementId.value = null
  editorName.value = scheme.name
  editorConfigs.value = cloneConfigs(scheme.configs)
  editorReadonly.value = !editable.value || scheme.status !== 'draft'
  editorConfigRelation.value = scheme.config_relation === 'alternative' ? 'alternative' : 'compose'
  editorPrimaryConfig.value = scheme.primary_config || ''
  if (editorConfigRelation.value === 'alternative' && !editorPrimaryConfig.value) {
    editorPrimaryConfig.value = editorConfigs.value[0]?.name || ''
  }
  editorOpen.value = true
}

function schemeMeta(scheme: BomScheme) {
  const qty = (scheme.configs || []).reduce((sum, cfg) => sum + Number(cfg.qty || 0), 0)
  const configNames = (scheme.configs || []).map((cfg) => cfg.name).filter(Boolean)
  const models = [...new Set((scheme.configs || []).map((cfg) => cfg.server_model).filter(Boolean))]
  return `${configNames.length} 个配置页签 · ${qty} 台${models.length ? ` · ${models.join(' / ')}` : ''}`
}

function statusLabel(status: BomScheme['status']) {
  return { draft: '草稿', current: '当前方案', archived: '已归档' }[status]
}

async function saveDraft() {
  if (!editorName.value.trim()) {
    message.warning('请填写方案名称')
    return
  }
  const configs = editorRef.value?.getConfigs() || []
  if (!configs.length) {
    message.warning('方案内至少保留一个配置页签')
    return
  }
  saving.value = true
  try {
    await portalApi.saveBomSchemeDraft(oppId.value, {
      scheme_id: editorSchemeId.value,
      expected_updated_at: editorUpdatedAt.value,
      flow_card_id: editorFlowCardId(),
      name: editorName.value.trim(),
      configs,
      config_relation: editorConfigRelation.value,
      primary_config: editorPrimaryConfig.value,
    })
    message.success('方案草稿已保存')
    editorOpen.value = false
    emit('changed')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存方案草稿失败')
  } finally {
    saving.value = false
  }
}

async function submitScheme() {
  if (!editorName.value.trim()) {
    message.warning('请填写方案名称')
    return
  }
  const configs = editorRef.value?.getConfigs() || []
  if (!configs.length) {
    message.warning('方案内容为空，无法提交')
    return
  }
  async function doSubmit(assigneeName: string) {
    const saved = await portalApi.saveBomSchemeDraft(oppId.value, {
      scheme_id: editorSchemeId.value,
      expected_updated_at: editorUpdatedAt.value,
      flow_card_id: editorFlowCardId(),
      name: editorName.value.trim(),
      configs,
      config_relation: editorConfigRelation.value,
      primary_config: editorPrimaryConfig.value,
    })
    editorSchemeId.value = saved.scheme.id
    await portalApi.submitBomScheme(oppId.value, saved.scheme.id, assigneeName)
  }
  async function runSubmit(assigneeName: string) {
    saving.value = true
    try {
      await doSubmit(assigneeName)
      message.success('方案已提交，流程进入成本核算')
      editorOpen.value = false
      emit('changed')
    } catch (e: any) {
      if (e?.response?.data?.detail === ASSIGNEE_REQUIRED_DETAIL) {
        promptAssignee('costing', '选择成本核算处理人', (name) => { runSubmit(name) })
        return
      }
      message.error(e.response?.data?.detail || '提交方案失败')
    } finally {
      saving.value = false
    }
  }
  Modal.confirm({
    title: '提交当前方案？',
    content: '提交后该方案进入成本核算，其他方案保留为草稿/归档；后续可回退重新编辑。',
    okText: '提交方案',
    cancelText: '取消',
    onOk: () => runSubmit(''),
  })
}

function deleteScheme(scheme: BomScheme) {
  const statusText = statusLabel(scheme.status)
  Modal.confirm({
    title: `删除${statusText}「${scheme.name}」？`,
    content: scheme.status === 'current'
      ? '当前方案删除后，需要重新提交新的方案才能进入成本核算。'
      : '删除后不可恢复。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const res = await portalApi.deleteBomScheme(oppId.value, scheme.id)
        if (!res.ok) {
          message.error('方案删除失败')
          return
        }
        message.success('方案已删除')
        emit('changed')
      } catch (e: any) {
        message.error(e.response?.data?.detail || '方案删除失败')
      }
    },
  })
}

function cardForScheme(scheme: BomScheme) {
  return cardFor('bom', scheme.id)
}

function returnScheme(scheme: BomScheme) {
  const card = cardForScheme(scheme)
  if (!card) return
  confirmWithReason({
    title: `退回方案「${scheme.name}」？`,
    hint: '退回后这张卡会回到方案配置节点，需要重新编辑并提交。',
    okText: '退回',
    placeholder: '请填写退回原因（必填），让对方知道需要修改什么',
    async onOk(reason) {
      const res = await portalApi.returnCard(oppId.value, card.id, reason)
      message.success('方案卡已退回')
      emit('card-updated', res.card)
    },
  })
}

function requestWithdrawScheme(scheme: BomScheme) {
  const card = cardForScheme(scheme)
  if (!card) return
  Modal.confirm({
    title: `申请撤回方案「${scheme.name}」？`,
    content: '仅当下游尚未保存、评论、传附件或继续流转时才能撤回。',
    okText: '申请撤回',
    cancelText: '取消',
    async onOk() {
      try {
        const res = await portalApi.requestWithdrawCard(oppId.value, card.id)
        message.success('撤回申请已提交')
        emit('card-updated', res.card)
      } catch (e: any) {
        message.error(e.response?.data?.detail || '撤回申请失败')
      }
    },
  })
}
</script>

<template>
  <div class="bom-workbench">
    <RecordTable
      title="方案"
      :empty="!schemes.length && !pendingRequirements.length"
      empty-text="尚无方案，点击“新建方案”开始配置。"
      :columns="[
        { label: '方案', width: '200px' },
        { label: '编号', width: '120px' },
        { label: '状态', width: '120px' },
        { label: '配置 / 台数 / 型号' },
        { label: '创建人 / 时间', width: '180px' },
        { label: '操作', width: '200px', align: 'right' },
      ]"
    >
      <tr
        v-for="req in pendingRequirements"
        :key="`pending-req-${req.version}`"
      >
        <td>
          <span class="rt-strong">需求单 v{{ req.version }}</span>
          <span class="rt-sub">来自线索登记</span>
        </td>
        <td class="rt-dim">REQ-{{ req.version }}</td>
        <td><span class="rt-badge rt-badge-current">待配方案</span></td>
        <td class="rt-dim">{{ req.slots?.server_model || '—' }}</td>
        <td class="rt-dim">{{ req.created_by || '—' }} · {{ (req.created_at || '').slice(5, 16) }}</td>
        <td>
          <div v-if="editable" class="rt-actions">
            <span class="rt-link" @click.stop="openSchemeForRequirement(req)">
              {{ schemeForRequirement(req) ? '查看方案' : '新建方案' }}
            </span>
          </div>
        </td>
      </tr>

      <tr
        v-for="scheme in schemes"
        :key="scheme.id"
        @click="openScheme(scheme)"
      >
        <td><span class="rt-strong">{{ scheme.name }}</span></td>
        <td class="rt-dim">BOM-{{ scheme.id }}</td>
        <td>
          <span class="rt-badge"
            :class="scheme.status === 'current' ? 'rt-badge-current' : scheme.status === 'draft' ? 'rt-badge-draft' : 'rt-badge-done'"
          >{{ statusLabel(scheme.status) }}</span>
        </td>
        <td>{{ schemeMeta(scheme) }}</td>
        <td class="rt-dim">{{ scheme.created_by || '—' }} · {{ (scheme.updated_at || scheme.created_at || '').slice(5, 16) }}</td>
        <td>
          <div v-if="editable && scheme.status === 'draft'" class="rt-actions">
            <span class="rt-link" @click.stop="openScheme(scheme)">继续编辑</span>
            <span class="rt-link" @click.stop="openScheme(scheme)">提交方案</span>
            <span class="rt-link danger" @click.stop="deleteScheme(scheme)">删除草稿</span>
          </div>
          <div v-else-if="editable && scheme.status === 'current'" class="rt-actions">
            <span class="rt-link" @click.stop="openScheme(scheme)">查看方案</span>
            <span v-if="cardForScheme(scheme)?.current_node === 'costing'" class="rt-link" @click.stop="requestWithdrawScheme(scheme)">申请撤回</span>
            <span v-if="cardForScheme(scheme)?.current_node === 'boming' && cardForScheme(scheme)?.flow_status === 'returned'" class="rt-link danger" @click.stop="returnScheme(scheme)">退回方案</span>
            <span class="rt-link danger" @click.stop="deleteScheme(scheme)">删除当前方案</span>
          </div>
          <div v-else-if="editable && scheme.status === 'archived'" class="rt-actions">
            <span class="rt-link" @click.stop="openScheme(scheme)">查看归档</span>
            <span class="rt-link danger" @click.stop="deleteScheme(scheme)">删除归档</span>
          </div>
        </td>
      </tr>

    </RecordTable>

    <a-modal
      v-model:open="editorOpen"
      :title="editorReadonly ? '查看方案' : '编辑方案'"
      width="min(1180px, calc(100vw - 24px))"
      wrap-class-name="portal-sheet-modal"
      :footer="null"
      :body-style="{ padding: '14px', maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', overflowX: 'hidden' }"
      @cancel="editorOpen = false"
    >
      <div class="scheme-layout">
        <aside class="scheme-req-ref glass-light">
          <div class="scheme-req-head">
            <b>上游需求单{{ requirement ? ` v${requirement.version}` : '' }}</b>
            <span class="scheme-req-chip">只读参考</span>
          </div>
          <div v-if="requirement" class="scheme-req-body">
            <RequirementForm ref="reqRef" v-model:req-text="reqText" :readonly="true" />
          </div>
          <div v-else class="scheme-req-empty">暂无需求单</div>
        </aside>
        <div class="scheme-editor">
          <div class="scheme-name">
            <span>方案名称</span>
            <a-input v-if="!editorReadonly" v-model:value="editorName" placeholder="如 方案A / 标准方案" />
            <strong v-else>{{ editorName || '—' }}</strong>
          </div>
          <SchemeEditor
            ref="editorRef"
            :configs="editorConfigs"
            :readonly="editorReadonly"
            :show-toolbar="false"
            v-model:config-relation="editorConfigRelation"
            v-model:primary-config="editorPrimaryConfig"
          />
          <div v-if="!editorReadonly" class="scheme-actions">
            <a-button @click="editorOpen = false">取消</a-button>
            <a-button :loading="saving" @click="saveDraft">保存草稿</a-button>
            <a-button type="primary" :loading="saving" @click="submitScheme">提交方案</a-button>
          </div>
        </div>
      </div>
    </a-modal>
    <AssigneePickerModal
      v-model:value="pickerChosen"
      :open="pickerOpen"
      :title="pickerTitle"
      :options="pickerOptions"
      @confirm="confirmPicker()"
      @cancel="cancelPicker()"
    />
  </div>
</template>

<style scoped>
.bom-workbench {
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
.bw-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 12px 14px;
}
.bw-summary {
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.bw-muted {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.bw-footer-link {
  margin-left: 8px;
  font-size: 12px;
  color: var(--cpq-accent-primary);
  cursor: pointer;
}
.bw-footer-link.danger {
  color: var(--cpq-color-danger, #ff4d4f);
}
.row-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-glass-border);
  color: var(--cpq-text-secondary);
  font-size: 11px;
  white-space: nowrap;
}
.row-meta-item b {
  font-weight: 500;
  color: var(--cpq-text-muted);
}
.row-meta-item.muted {
  color: var(--cpq-text-muted);
  background: transparent;
  border: none;
  padding: 0 2px;
}
.bw-empty {
  grid-column: 1 / -1;
  padding: 40px 16px;
  text-align: center;
  color: var(--cpq-text-muted);
  font-size: 13px;
  border: 1px dashed var(--cpq-glass-border);
  border-radius: 12px;
}
.scheme-layout {
  display: grid;
  grid-template-columns: minmax(340px, 420px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  width: 100%;
}
.scheme-layout > * {
  min-width: 0;
}
.scheme-req-ref {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 230px);
  overflow: hidden;
}
.scheme-req-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding: 12px 14px;
  border-bottom: 1px solid var(--cpq-border-primary);
}
.scheme-req-head b {
  font-size: 14px;
  color: var(--cpq-text-primary);
}
.scheme-req-chip {
  border-radius: 999px;
  padding: 5px 11px;
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
  font-size: 12px;
  font-weight: 600;
}
.scheme-req-body {
  padding: 12px 14px;
  overflow: auto;
  min-height: 0;
}
.scheme-req-empty {
  padding: 20px 14px;
  color: var(--cpq-text-muted);
  font-size: 13px;
  text-align: center;
}
.scheme-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  max-height: calc(100vh - 230px);
  overflow: auto;
}
.scheme-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.scheme-name .ant-input {
  max-width: 300px;
}
.scheme-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
}
@media (max-width: 980px) {
  .scheme-layout {
    grid-template-columns: 1fr;
  }
}
</style>
