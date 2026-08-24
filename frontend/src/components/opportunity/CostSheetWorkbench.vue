<script setup lang="ts">
import { computed, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import DocumentCard from '@/components/flow/DocumentCard.vue'
import CostSheetEditor from '@/components/opportunity/CostSheetEditor.vue'
import { portalApi, type BomScheme, type CostSheet, type FlowCard, type PortalBoard, type PortalSheetConfig } from '@/api/portal'

const props = defineProps<{
  board: PortalBoard
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'card-updated', card: FlowCard): void
  (e: 'open-archive', payload: { categories: string[]; title: string }): void
  (e: 'upload-cost-sheet'): void
}>()

const oppId = computed(() => props.board.opportunity?.opportunity_id || '')
const sheets = computed(() => props.board.cost_sheets || [])
const bomSchemes = computed(() => props.board.bom_schemes || [])
const editable = computed(() => !props.readonly)
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

function claimBom(bom: BomScheme) {
  const card = cardFor('bom', bom.id)
  if (card) claimCard(card)
}

function editorFlowCardId() {
  const existing = cardFor('cost', editorSheetId.value)
  return existing?.id ?? cardFor('bom', editorBomSchemeId.value)?.id ?? null
}

const pendingBomSchemes = computed(() =>
  bomSchemes.value.filter((bom) => {
    const card = cardFor('bom', bom.id)
    return card?.current_node === 'costing' && ['submitted', 'processing'].includes(card.flow_status)
  }),
)

function costSheetForBom(bomId: number | null | undefined): CostSheet | null {
  if (!bomId) return null
  return sheets.value.find((sheet) => sheet.bom_scheme_id === bomId && sheet.status !== 'archived') || null
}

function openCostForBom(bom: BomScheme) {
  const sheet = costSheetForBom(bom.id)
  if (sheet) openSheet(sheet)
  else openNewForBom(bom)
}

const editorOpen = ref(false)
const editorSheetId = ref<number | null>(null)
const editorBomSchemeId = ref<number | null>(null)
const editorName = ref('')
const editorConfigs = ref<PortalSheetConfig[]>([])
const editorReadonly = ref(false)
const editorRef = ref<InstanceType<typeof CostSheetEditor> | null>(null)
const saving = ref(false)

function cloneConfigs(configs: PortalSheetConfig[]) {
  return JSON.parse(JSON.stringify(configs || [])) as PortalSheetConfig[]
}

function ensureCostFields(configs: PortalSheetConfig[]) {
  return cloneConfigs(configs).map((cfg) => ({
    ...cfg,
    l6_cost: cfg.l6_cost ?? 0,
    l6_margin: cfg.l6_margin ?? 0,
    l6_rows: (cfg.l6_rows || []).map((row) => ({ ...row, base_price: row.base_price ?? 0 })),
    kp_rows: (cfg.kp_rows || []).map((row) => ({ ...row, base_price: row.base_price ?? 0 })),
  }))
}

function openNew() {
  if (!editable.value) return
  const first = pendingBomSchemes.value[0]
  if (!first) {
    message.warning('当前没有待核价的 BOM 方案，无法新建成本表')
    return
  }
  openNewForBom(first)
}

function openNewForBom(bom: BomScheme) {
  if (!editable.value) return
  if (!bom.configs?.length) {
    message.warning('该 BOM 方案没有配置页签，无法新建成本表')
    return
  }
  editorSheetId.value = null
  editorBomSchemeId.value = bom.id
  editorName.value = `成本-${bom.name}`
  editorConfigs.value = ensureCostFields(bom.configs)
  editorReadonly.value = false
  editorOpen.value = true
}

function openSheet(sheet: CostSheet) {
  editorSheetId.value = sheet.id
  editorBomSchemeId.value = sheet.bom_scheme_id
  editorName.value = sheet.name
  editorConfigs.value = cloneConfigs(sheet.configs)
  editorReadonly.value = !editable.value || sheet.status !== 'draft'
  editorOpen.value = true
}

function statusLabel(status: CostSheet['status']) {
  return { draft: '草稿', current: '当前成本表', archived: '已归档' }[status]
}

function sheetMeta(sheet: CostSheet) {
  const configs = sheet.configs || []
  const qty = configs.reduce((sum, cfg) => sum + Number(cfg.qty || 0), 0)
  const totalCost = configs.reduce((sum, cfg) => {
    const kpCost = (cfg.kp_rows || []).reduce((acc, row) => acc + Number(row.base_price || 0) * Number(row.qty || 0), 0)
    return sum + (Number(cfg.l6_cost || 0) + kpCost) * Number(cfg.qty || 0)
  }, 0)
  return `${configs.length} 个配置页签 · ${qty} 台 · 成本 ¥${totalCost.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

async function saveDraft() {
  if (!editorName.value.trim()) {
    message.warning('请填写成本表名称')
    return
  }
  const configs = editorRef.value?.getConfigs() || []
  if (!configs.length) {
    message.warning('成本表内至少保留一个配置页签')
    return
  }
  saving.value = true
  try {
    await portalApi.saveCostSheetDraft(oppId.value, {
      sheet_id: editorSheetId.value,
      flow_card_id: editorFlowCardId(),
      name: editorName.value.trim(),
      configs,
      bom_scheme_id: editorBomSchemeId.value,
    })
    message.success('成本表草稿已保存')
    editorOpen.value = false
    emit('changed')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存成本表草稿失败')
  } finally {
    saving.value = false
  }
}

async function submitSheet() {
  if (!editorName.value.trim()) {
    message.warning('请填写成本表名称')
    return
  }
  const configs = editorRef.value?.getConfigs() || []
  if (!configs.length) {
    message.warning('成本表内容为空，无法提交')
    return
  }
  Modal.confirm({
    title: '提交当前成本表？',
    content: '提交后将生成报价单草稿并进入报价单节点，其他成本表保留为草稿/归档。',
    okText: '提交成本表',
    cancelText: '取消',
    async onOk() {
      saving.value = true
      try {
        const saved = await portalApi.saveCostSheetDraft(oppId.value, {
          sheet_id: editorSheetId.value,
          flow_card_id: editorFlowCardId(),
          name: editorName.value.trim(),
          configs,
          bom_scheme_id: editorBomSchemeId.value,
        })
        await portalApi.submitCostSheet(oppId.value, saved.sheet.id)
        message.success('成本表已提交，流程进入报价单节点')
        editorOpen.value = false
        emit('changed')
      } catch (e: any) {
        message.error(e.response?.data?.detail || '提交成本表失败')
      } finally {
        saving.value = false
      }
    },
  })
}

function deleteSheet(sheet: CostSheet) {
  Modal.confirm({
    title: `删除成本表草稿「${sheet.name}」？`,
    content: '删除后不可恢复；已提交或已归档成本表不会提供删除入口。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await portalApi.deleteCostSheet(oppId.value, sheet.id)
        message.success('成本表草稿已删除')
        emit('changed')
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除成本表草稿失败')
      }
    },
  })
}

function cardForSheet(sheet: CostSheet) {
  return cardFor('cost', sheet.id)
}

function requestWithdrawSheet(sheet: CostSheet) {
  const card = cardForSheet(sheet)
  if (!card) return
  Modal.confirm({
    title: `申请撤回成本表「${sheet.name}」？`,
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

function returnSheet(sheet: CostSheet) {
  const card = cardForSheet(sheet)
  if (!card) return
  Modal.confirm({
    title: `退回成本表「${sheet.name}」？`,
    content: '退回后这张卡会回到成本核算节点，需要重新计算并提交。',
    okText: '退回',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const res = await portalApi.returnCard(oppId.value, card.id)
        message.success('成本卡已退回')
        emit('card-updated', res.card)
      } catch (e: any) {
        message.error(e.response?.data?.detail || '退回失败')
      }
    },
  })
}
</script>

<template>
  <div class="cost-workbench">
    <header class="cw-head">
      <div>
        <span class="cw-eyebrow">成本核算</span>
        <h3>成本核算工作区</h3>
      </div>
      <div class="cw-head-actions">
        <a-button size="small" @click="emit('open-archive', { categories: ['requirement'], title: '成本附件' })">成本附件</a-button>
        <a-button v-if="editable" type="primary" size="small" @click="emit('upload-cost-sheet')">上传成本表</a-button>
        <a-button v-if="editable" type="primary" size="small" @click="openNew">新建成本表</a-button>
      </div>
    </header>

    <div class="cw-grid">
      <DocumentCard
        v-for="bom in pendingBomSchemes"
        :key="`pending-bom-${bom.id}`"
        :title="`待核价 · ${bom.name}`"
        doc-no="待处理 · 来自方案配置"
        status="待核价"
        status-tone="current"
        doc-type="bom"
        :active="editorBomSchemeId === bom.id"
      >
        <template #summary>
          <div class="cw-summary">{{ bom.configs?.length || 0 }} 个配置页签 · 来自方案配置节点</div>
          <div class="cw-muted">{{ bom.created_by || '—' }} · {{ (bom.updated_at || bom.created_at || '').slice(5, 16) }}</div>
        </template>
        <template v-if="editable" #footer>
          <span v-if="canClaim(cardFor('bom', bom.id))" class="cw-footer-link" @click.stop="claimBom(bom)">认领</span>
          <span class="cw-footer-link primary" @click.stop="openCostForBom(bom)">
            {{ costSheetForBom(bom.id) ? '继续核算' : '新建成本表' }}
          </span>
        </template>
      </DocumentCard>

      <DocumentCard
        v-for="sheet in sheets"
        :key="sheet.id"
        :title="sheet.name"
        :doc-no="`COST-${sheet.id}`"
        :status="statusLabel(sheet.status)"
        :status-tone="sheet.status === 'current' ? 'current' : sheet.status === 'draft' ? 'draft' : 'done'"
        doc-type="cost"
        :active="sheet.status === 'current'"
        @click="openSheet(sheet)"
      >
        <template #summary>
          <div class="cw-summary">{{ sheetMeta(sheet) }}</div>
          <div class="cw-muted">{{ sheet.created_by || '—' }} · {{ (sheet.updated_at || sheet.created_at || '').slice(5, 16) }}</div>
        </template>
        <template v-if="editable && sheet.status === 'draft'" #footer>
          <span class="cw-footer-link" @click.stop="openSheet(sheet)">继续编辑</span>
          <span class="cw-footer-link primary" @click.stop="openSheet(sheet)">提交成本表</span>
          <span class="cw-footer-link danger" @click.stop="deleteSheet(sheet)">删除草稿</span>
        </template>
        <template v-else-if="editable && sheet.status === 'current'" #footer>
          <span class="cw-footer-link" @click.stop="openSheet(sheet)">查看成本表</span>
          <span v-if="cardForSheet(sheet)?.current_node === 'quoting'" class="cw-footer-link" @click.stop="requestWithdrawSheet(sheet)">申请撤回</span>
          <span v-if="cardForSheet(sheet)?.current_node === 'costing' && cardForSheet(sheet)?.flow_status === 'returned'" class="cw-footer-link danger" @click.stop="returnSheet(sheet)">退回成本表</span>
          <span class="cw-footer-link danger" @click.stop="deleteSheet(sheet)">删除当前成本表</span>
        </template>
      </DocumentCard>

      <div v-if="!sheets.length" class="cw-empty">
        {{ pendingBomSchemes.length ? '尚无成本表，点击“新建成本表”从待核价 BOM 方案生成。' : '尚无成本表；请先在方案配置节点提交一个 BOM 方案。' }}
      </div>
    </div>

    <a-modal
      v-model:open="editorOpen"
      :title="editorReadonly ? '查看成本表' : '编辑成本表'"
      width="min(1000px, 96vw)"
      wrap-class-name="portal-sheet-modal"
      :footer="null"
      :body-style="{ padding: '14px', maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', overflowX: 'hidden' }"
      @cancel="editorOpen = false"
    >
      <div class="cost-editor">
        <div class="cost-name">
          <span>成本表名称</span>
          <a-input v-if="!editorReadonly" v-model:value="editorName" placeholder="如 成本-方案A" />
          <strong v-else>{{ editorName || '—' }}</strong>
        </div>
        <CostSheetEditor
          ref="editorRef"
          :configs="editorConfigs"
          :readonly="editorReadonly"
          :show-toolbar="false"
        />
        <div v-if="!editorReadonly" class="cost-actions">
          <a-button @click="editorOpen = false">取消</a-button>
          <a-button :loading="saving" @click="saveDraft">保存草稿</a-button>
          <a-button type="primary" :loading="saving" @click="submitSheet">提交成本表</a-button>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.cost-workbench {
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
.cw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.cw-eyebrow {
  display: block;
  color: var(--cpq-text-muted);
  font-size: 11px;
  letter-spacing: 0.06em;
}
.cw-head h3 {
  margin: 2px 0 0;
  color: var(--cpq-text-primary);
  font-size: 14px;
}
.cw-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cw-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 12px 14px;
}
.cw-summary {
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.cw-muted {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.cw-footer-link {
  margin-left: 8px;
  font-size: 12px;
  color: var(--cpq-accent-primary);
  cursor: pointer;
}
.cw-footer-link.danger {
  color: var(--cpq-color-danger, #ff4d4f);
}
.cw-empty {
  grid-column: 1 / -1;
  padding: 40px 16px;
  text-align: center;
  color: var(--cpq-text-muted);
  font-size: 13px;
  border: 1px dashed var(--cpq-glass-border);
  border-radius: 12px;
}
.cost-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cost-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.cost-name .ant-input {
  max-width: 300px;
}
.cost-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
}
</style>
