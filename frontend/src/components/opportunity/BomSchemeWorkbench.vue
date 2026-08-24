<script setup lang="ts">
import { computed, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import DocumentCard from '@/components/flow/DocumentCard.vue'
import SchemeEditor from '@/components/opportunity/SchemeEditor.vue'
import RequirementContextPanel from '@/components/opportunity/RequirementContextPanel.vue'
import { portalApi, type BomScheme, type FlowCard, type PortalBoard, type PortalSheetConfig } from '@/api/portal'
import AttachmentUploadButton from '@/components/opportunity/AttachmentUploadButton.vue'

const props = defineProps<{
  board: PortalBoard
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'card-updated', card: FlowCard): void
  (e: 'open-archive', payload: { categories: string[]; title: string }): void
}>()

const oppId = computed(() => props.board.opportunity?.opportunity_id || '')
const schemes = computed(() => props.board.bom_schemes || [])
const editable = computed(() => !props.readonly)
const requirements = computed(() => props.board.requirements || [])
const requirement = computed(() => props.board.requirement || props.board.requirements?.find((r) => r.status === 'current') || null)
const flowCards = computed(() => props.board.flow_cards || [])

function cardFor(type: FlowCard['entities'][number]['entity_type'], entityId: number | string | null | undefined): FlowCard | undefined {
  if (entityId === null || entityId === undefined || entityId === '') return undefined
  return flowCards.value.find((card) => card.entities.some((e) => e.entity_type === type && e.entity_id === String(entityId)))
}

function canClaim(card: FlowCard | undefined): boolean {
  return Boolean(card?.can_claim)
}

async function claimCard(card: FlowCard) {
  try {
    const res = await portalApi.claimCard(oppId.value, card.id)
    message.success('已认领该卡')
    emit('card-updated', res.card)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '认领失败')
  }
}

function claimRequirement(req: { version: number }) {
  const card = cardFor('requirement', req.version)
  if (card) claimCard(card)
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
const editorSchemeId = ref<number | null>(null)
const editorSourceRequirementId = ref<number | null>(null)
const editorName = ref('')
const editorConfigs = ref<PortalSheetConfig[]>([])
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

function openNew() {
  if (!editable.value) return
  editorSchemeId.value = null
  editorSourceRequirementId.value = null
  editorName.value = ''
  editorConfigs.value = [blankConfig('CFG1')]
  editorReadonly.value = false
  editorOpen.value = true
}

function openNewForRequirement(req: { version: number }) {
  if (!editable.value) return
  editorSchemeId.value = null
  editorSourceRequirementId.value = cardFor('requirement', req.version)?.id || null
  editorName.value = ''
  editorConfigs.value = [blankConfig('CFG1')]
  editorReadonly.value = false
  editorOpen.value = true
}

function openScheme(scheme: BomScheme) {
  editorSchemeId.value = scheme.id
  editorSourceRequirementId.value = null
  editorName.value = scheme.name
  editorConfigs.value = cloneConfigs(scheme.configs)
  editorReadonly.value = !editable.value || scheme.status !== 'draft'
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
      flow_card_id: editorFlowCardId(),
      name: editorName.value.trim(),
      configs,
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
  Modal.confirm({
    title: '提交当前方案？',
    content: '提交后该方案进入成本核算，其他方案保留为草稿/归档；后续可回退重新编辑。',
    okText: '提交方案',
    cancelText: '取消',
    async onOk() {
      saving.value = true
      try {
        const saved = await portalApi.saveBomSchemeDraft(oppId.value, {
          scheme_id: editorSchemeId.value,
          flow_card_id: editorFlowCardId(),
          name: editorName.value.trim(),
          configs,
        })
        await portalApi.submitBomScheme(oppId.value, saved.scheme.id)
        message.success('方案已提交，流程进入成本核算')
        editorOpen.value = false
        emit('changed')
      } catch (e: any) {
        message.error(e.response?.data?.detail || '提交方案失败')
      } finally {
        saving.value = false
      }
    },
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
  Modal.confirm({
    title: `退回方案「${scheme.name}」？`,
    content: '退回后这张卡会回到方案配置节点，需要重新编辑并提交。',
    okText: '退回',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const res = await portalApi.returnCard(oppId.value, card.id)
        message.success('方案卡已退回')
        emit('card-updated', res.card)
      } catch (e: any) {
        message.error(e.response?.data?.detail || '退回失败')
      }
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
    <header class="bw-head">
      <div>
        <span class="bw-eyebrow">方案配置</span>
        <h3>BOM 方案工作区</h3>
      </div>
      <div class="bw-head-actions">
        <AttachmentUploadButton :opportunity-id="oppId" category="technical" label="上传附件" />
        <a-button size="small" @click="emit('open-archive', { categories: ['technical'], title: '方案附件' })">方案附件</a-button>
        <a-button v-if="editable" type="primary" size="small" @click="openNew">新建方案</a-button>
      </div>
    </header>

    <div class="bw-grid">
      <DocumentCard
        v-for="req in pendingRequirements"
        :key="`pending-req-${req.version}`"
        :title="`待配方案 · 需求单 v${req.version}`"
        doc-no="待处理 · 来自线索登记"
        status="待配方案"
        status-tone="current"
        doc-type="requirement"
        :active="editorSourceRequirementId === cardFor('requirement', req.version)?.id"
      >
        <template #summary>
          <div class="bw-summary">来自线索登记节点，提交后进入成本核算</div>
          <div class="bw-muted">{{ req.created_by || '—' }} · {{ (req.created_at || '').slice(5, 16) }}</div>
        </template>
        <template v-if="editable" #footer>
          <span v-if="canClaim(cardFor('requirement', req.version))" class="bw-footer-link" @click.stop="claimRequirement(req)">认领</span>
          <span class="bw-footer-link primary" @click.stop="openSchemeForRequirement(req)">
            {{ schemeForRequirement(req) ? '查看方案' : '新建方案' }}
          </span>
        </template>
      </DocumentCard>

      <DocumentCard
        v-for="scheme in schemes"
        :key="scheme.id"
        :title="scheme.name"
        :doc-no="`BOM-${scheme.id}`"
        :status="statusLabel(scheme.status)"
        :status-tone="scheme.status === 'current' ? 'current' : scheme.status === 'draft' ? 'draft' : 'done'"
        doc-type="bom"
        :active="scheme.status === 'current'"
        @click="openScheme(scheme)"
      >
        <template #summary>
          <div class="bw-summary">{{ schemeMeta(scheme) }}</div>
          <div class="bw-muted">{{ scheme.created_by || '—' }} · {{ (scheme.updated_at || scheme.created_at || '').slice(5, 16) }}</div>
        </template>
        <template v-if="editable && scheme.status === 'draft'" #footer>
          <span class="bw-footer-link" @click.stop="openScheme(scheme)">继续编辑</span>
          <span class="bw-footer-link primary" @click.stop="openScheme(scheme)">提交方案</span>
          <span class="bw-footer-link danger" @click.stop="deleteScheme(scheme)">删除草稿</span>
        </template>
        <template v-else-if="editable && scheme.status === 'current'" #footer>
          <span class="bw-footer-link" @click.stop="openScheme(scheme)">查看方案</span>
          <span v-if="cardForScheme(scheme)?.current_node === 'costing'" class="bw-footer-link" @click.stop="requestWithdrawScheme(scheme)">申请撤回</span>
          <span v-if="cardForScheme(scheme)?.current_node === 'boming' && cardForScheme(scheme)?.flow_status === 'returned'" class="bw-footer-link danger" @click.stop="returnScheme(scheme)">退回方案</span>
          <span class="bw-footer-link danger" @click.stop="deleteScheme(scheme)">删除当前方案</span>
        </template>
        <template v-else-if="editable && scheme.status === 'archived'" #footer>
          <span class="bw-footer-link" @click.stop="openScheme(scheme)">查看归档</span>
          <span class="bw-footer-link danger" @click.stop="deleteScheme(scheme)">删除归档</span>
        </template>
      </DocumentCard>

      <div v-if="!schemes.length" class="bw-empty">
        尚无方案，点击“新建方案”开始配置。
      </div>
    </div>

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
        <RequirementContextPanel :requirement="requirement" />
        <div class="scheme-editor">
          <div class="scheme-name">
            <span>方案名称</span>
            <a-input v-if="!editorReadonly" v-model:value="editorName" placeholder="如 方案A / 标准方案" />
            <strong v-else>{{ editorName || '—' }}</strong>
          </div>
          <SchemeEditor
            ref="editorRef"
            :configs="editorConfigs"
            stage="boming"
            :readonly="editorReadonly"
            :show-toolbar="false"
          />
          <div v-if="!editorReadonly" class="scheme-actions">
            <a-button @click="editorOpen = false">取消</a-button>
            <a-button :loading="saving" @click="saveDraft">保存草稿</a-button>
            <a-button type="primary" :loading="saving" @click="submitScheme">提交方案</a-button>
          </div>
        </div>
      </div>
    </a-modal>
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
.bw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.bw-eyebrow {
  display: block;
  color: var(--cpq-text-muted);
  font-size: 11px;
  letter-spacing: 0.06em;
}
.bw-head h3 {
  margin: 2px 0 0;
  color: var(--cpq-text-primary);
  font-size: 14px;
}
.bw-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  width: 100%;
}
.scheme-layout > * {
  min-width: 0;
}
.scheme-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  overflow: hidden;
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
