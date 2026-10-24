<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { portalApi } from '@/api/portal'
import { projectApi } from '@/api'
import { useAuthStore } from '@/store/auth'
import CostSheetEditor from '@/components/opportunity/CostSheetEditor.vue'
import SchemeEditor from '@/components/opportunity/SchemeEditor.vue'
import ShareDialog from '@/components/opportunity/ShareDialog.vue'

/**
 * 产物卡（kind='artifact'）：聊天内只留收起态摘要卡，点击开宽幅抽屉看内容——
 * 查看器=现成生产组件的薄容器（CostSheetEditor readonly / QuoteWorkbench / SchemeEditor），
 * refs 只存 id，打开抽屉时按 ref 拉活数据——权限在拉取时生效，卡片不携带业务数据。
 * 弹窗宽度桌面 min(1080px,94vw) 居中 / 手机全屏：生产组件按它们在详情页的全宽渲染，聊天流不再被撑破。
 * autoOpen：画布「输出物」等宿主复用时只渲染弹窗本体并立即打开（不显示收起态头）。
 */
const props = defineProps<{ card: Record<string, any>; autoOpen?: boolean }>()

const router = useRouter()
const auth = useAuthStore()
const drawerOpen = ref(false)
const refs = computed<Record<string, any>>(() => props.card?.refs || {})

const TYPE_ICON: Record<string, string> = {
  cost_sheet_parse: '📊', quotation: '🧾', share_link: '🔗',
}
const icon = computed(() => TYPE_ICON[props.card?.artifact_type] || '📎')
const isMobile = computed(() => window.innerWidth < 768)
const modalWidth = computed(() => (isMobile.value ? '100vw' : 'min(1080px, 94vw)'))

/* 从卡片跳页：先关卡片弹窗再跳——弹窗开着时跳转发生在弹窗底下的页面上，看起来毫无反应
   （2026-10-22 用户实测：点行/按钮/链接全都"没反应"的根源之一）。 */
function goToDetail() {
  drawerOpen.value = false
  const oppId = refs.value.opportunity_id
  if (oppId) router.push(`/opportunities/${oppId}`)
}
/* 点报价单行 = 商机详情页同语义（未导出草稿 → 报价工作台编辑），先关卡片弹窗再跳。 */
function openQuotationRow(q: any) {
  drawerOpen.value = false
  const opp = refs.value.opportunity_id
  const qid = String(q?.quotation_id || refs.value.quotation_id || '')
  if (opp) router.push(`/workspace?opportunityId=${opp}&quotationId=${qid}&mode=edit&from=opportunities`)
}

/* ── cost_sheet_parse：CostSheetEditor（readonly，可切换编辑并保存） ── */
const sheet = ref<any>(null)
const sheetLoading = ref(false)
const sheetEditing = ref(false)
const sheetSaving = ref(false)
const editorRef = ref<InstanceType<typeof CostSheetEditor> | null>(null)

async function loadSheet() {
  const oppId = refs.value.opportunity_id
  if (sheet.value || sheetLoading.value || !oppId || !refs.value.sheet_id) return
  sheetLoading.value = true
  try {
    const r = await portalApi.listCostSheets(oppId)
    sheet.value = (r.cost_sheets || []).find(
      (s: any) => Number(s.id ?? s.sheet_id) === Number(refs.value.sheet_id)) || null
  } catch {
    message.warning('成本表加载失败')
  } finally {
    sheetLoading.value = false
  }
}
async function saveSheet() {
  if (!sheet.value) return
  const configs = editorRef.value?.getConfigs() || []
  if (!configs.length) { message.warning('成本表内至少保留一个配置页签'); return }
  sheetSaving.value = true
  try {
    await portalApi.saveCostSheetDraft(refs.value.opportunity_id, {
      sheet_id: sheet.value.sheet_id,
      expected_updated_at: sheet.value.updated_at,
      name: sheet.value.name,
      configs,
      bom_scheme_id: sheet.value.bom_scheme_id ?? undefined,
      quotation_id: sheet.value.quotation_id || undefined,
    })
    message.success('成本表已保存')
    sheetEditing.value = false
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    sheetSaving.value = false
  }
}

/* ── bom_scheme：SchemeEditor（商机详情页方案配置表同款，readonly 打开可切编辑保存） ── */
const scheme = ref<any>(null)
const schemeLoading = ref(false)
const schemeEditing = ref(false)
const schemeSaving = ref(false)
const schemeEditorRef = ref<InstanceType<typeof SchemeEditor> | null>(null)

async function loadScheme() {
  const oppId = refs.value.opportunity_id
  if (scheme.value || schemeLoading.value || !oppId || !refs.value.bom_scheme_id) return
  schemeLoading.value = true
  try {
    const r = await portalApi.listBomSchemes(oppId)
    scheme.value = (r.bom_schemes || []).find(
      (x: any) => Number(x.id ?? x.bom_scheme_id) === Number(refs.value.bom_scheme_id)) || null
  } catch {
    message.warning('方案表加载失败')
  } finally {
    schemeLoading.value = false
  }
}
async function onSchemeSave(p: { configs: any[] }) {
  if (!scheme.value) return
  if (!p.configs.length) { message.warning('方案表内至少保留一个配置页签'); return }
  schemeSaving.value = true
  try {
    await portalApi.saveBomSchemeDraft(refs.value.opportunity_id, {
      scheme_id: Number(scheme.value.bom_scheme_id ?? scheme.value.id),
      expected_updated_at: scheme.value.updated_at,
      name: scheme.value.name,
      configs: p.configs,
    })
    message.success('方案表已保存')
    schemeEditing.value = false
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    schemeSaving.value = false
  }
}

/* ── quotation：QuoteWorkbench（价格列显隐=组件现成 prop） ── */
const QuoteWorkbench = defineAsyncComponent(() => import('@/components/opportunity/QuoteWorkbench.vue'))
const board = ref<any>(null)
const quotations = ref<any[]>([])
const quoteLoading = ref(false)
const canSeePrice = computed(() => auth.can('field.opportunity.quote_price'))
const priceVisible = ref(canSeePrice.value)
const quoteContext = computed(() => board.value?.quote_context)
/* 上游成本面板折叠态：QuoteWorkbench 是 v-model 双向绑定（此前传死值 false，
   点展开头只发出事件没人接，看起来"点了没反应"）。 */
const upstreamOpen = ref(false)
/* QuoteWorkbench 的下拉菜单等弹出层挂进当前弹窗容器：teleport body 的默认层级
   （1050）会被产物卡弹窗（2000）压住——「更多」菜单开了也在身后。closest 兼容两个宿主。 */
const popupInModal = (trigger: HTMLElement) =>
  trigger.closest('.ant-modal-content') as HTMLElement | null || document.body

async function loadQuote() {
  const oppId = refs.value.opportunity_id
  if (board.value || quoteLoading.value || !oppId) return
  quoteLoading.value = true
  try {
    const [b, proj] = await Promise.all([
      portalApi.board(oppId),
      projectApi.getById(oppId).catch(() => null),
    ])
    board.value = b
    quotations.value = proj?.quotations || []
  } catch {
    message.warning('报价单加载失败')
  } finally {
    quoteLoading.value = false
  }
}

/* ── 分享/导出：复用人工分享的 ShareDialog（版本选择自带：方案/成本/客户外发走审批） ── */
const shareDialogOpen = ref(false)

/* ── share_link ── */
const shareUrl = computed(() => refs.value.share_path || '')
async function copyShare() {
  try {
    await navigator.clipboard.writeText(location.origin + shareUrl.value)
    message.success('链接已复制')
  } catch {
    message.warning('复制失败，请手动复制')
  }
}

watch(drawerOpen, (v) => {
  if (!v) return
  if (props.card?.artifact_type === 'cost_sheet_parse') loadSheet()
  if (props.card?.artifact_type === 'bom_scheme') loadScheme()
  if (props.card?.artifact_type === 'quotation') loadQuote()
}, { immediate: true })
if (props.autoOpen) drawerOpen.value = true
</script>

<template>
  <div class="artifact-card">
    <button v-if="!autoOpen" type="button" class="ac-head" @click="drawerOpen = true">
      <span class="ac-icon">{{ icon }}</span>
      <span class="ac-meta">
        <span class="ac-title">{{ card.title }}</span>
        <span class="ac-sub">{{ card.summary }}</span>
      </span>
      <span class="ac-view">查看</span>
    </button>

    <a-modal
      v-model:open="drawerOpen"
      :title="(icon + ' ' + card.title).trim()"
      :width="modalWidth"
      :footer="null"
      destroy-on-close
      :z-index="2000"
      :wrap-class-name="'artifact-modal-wrap ' + (isMobile ? 'artifact-modal-full' : '')"
      style="top: 40px"
    >
      <!-- 成本表解析：CostSheetEditor（readonly，可切编辑） -->
      <template v-if="card.artifact_type === 'cost_sheet_parse'">
        <div v-if="sheetLoading" class="ac-loading">加载中…</div>
        <template v-else-if="sheet">
          <div class="ac-toolbar">
            <a-checkbox v-model:checked="sheetEditing">编辑模式</a-checkbox>
            <span class="deep-link" @click="goToDetail">去商机详情 →</span>
          </div>
          <CostSheetEditor
            ref="editorRef"
            :configs="sheet.configs || []"
            :readonly="!sheetEditing"
          />
          <div v-if="sheetEditing" class="ac-foot">
            <a-button @click="sheetEditing = false">取消</a-button>
            <a-button type="primary" :loading="sheetSaving" @click="saveSheet">保存修改</a-button>
          </div>
        </template>
        <a-empty v-else description="未找到成本表草稿（可能仅解析预览未落库）" />
      </template>

      <!-- 方案表：SchemeEditor（商机详情页方案配置表同款，readonly 打开可切编辑保存） -->
      <template v-else-if="card.artifact_type === 'bom_scheme'">
        <div v-if="schemeLoading" class="ac-loading">加载中…</div>
        <template v-else-if="scheme">
          <div class="ac-toolbar">
            <a-checkbox v-model:checked="schemeEditing">编辑模式</a-checkbox>
            <span class="deep-link" @click="goToDetail">去商机详情 →</span>
          </div>
          <SchemeEditor
            ref="schemeEditorRef"
            :configs="scheme.configs || []"
            :readonly="!schemeEditing"
            @save="onSchemeSave"
          />
        </template>
        <a-empty v-else description="未找到方案表草稿" />
      </template>

      <!-- 报价单：QuoteWorkbench（价格列显隐=组件现成 prop） -->
      <template v-else-if="card.artifact_type === 'quotation'">
        <div v-if="quoteLoading" class="ac-loading">加载中…</div>
        <template v-else-if="board && quoteContext">
          <div class="ac-toolbar">
            <a-checkbox v-model:checked="priceVisible" :disabled="!canSeePrice">显示成本 / 利润</a-checkbox>
            <a-button type="primary" size="small" @click="shareDialogOpen = true">分享 / 导出</a-button>
            <span class="deep-link" @click="goToDetail">去工作台编辑 →</span>
          </div>
          <QuoteWorkbench
            :board="board"
            :quote-context="quoteContext"
            :quotations="quotations"
            :quote-price-visible="priceVisible"
            v-model:upstream-open="upstreamOpen"
            :popup-container="popupInModal"
            :host-z-index="2100"
            @new-quotation="goToDetail"
            @view-quotation="openQuotationRow"
            @unfreeze-quotation="goToDetail"
            @set-primary="goToDetail"
            @rename-quotation="goToDetail"
            @delete-quotation="goToDetail"
            @enter-quote-batch="goToDetail"
            @batch-delete-quotes="goToDetail"
            @convert-cost-to-quotation="goToDetail"
            @delete-cost-sheet="goToDetail"
          />
        </template>
        <a-empty v-else description="报价单加载失败，请稍后重试" />
      </template>

      <!-- 分享链接 -->
      <template v-else-if="card.artifact_type === 'share_link'">
        <div class="share-row">
          <code class="share-path">{{ shareUrl }}</code>
          <a-button @click="copyShare">复制链接</a-button>
          <a-button type="primary" @click="goToDetail">去商机查看</a-button>
        </div>
      </template>

      <div v-else class="ac-loading">{{ card.summary }}</div>

      <!-- 人工分享同一个对话框：版本选择/链接/有效期都在里面，用户自己选
           （挂在条件链之后：组件不能夹在 v-if/v-else-if 分支中间，会打断链导致模板编译失败） -->
      <ShareDialog
        v-model:open="shareDialogOpen"
        :z-index="2100"
        :opportunity-id="refs.opportunity_id || ''"
        source-type="quote"
        :source-id="refs.quotation_id || ''"
        :title="card.title"
        default-view="scheme"
      />
    </a-modal>
  </div>
</template>

<style scoped>
.artifact-card { background: var(--cpq-glass-card-bg, rgba(255,255,255,0.9));
  border: 1px solid var(--cpq-border-primary, rgba(22,119,255,0.10));
  border-radius: var(--cpq-radius-lg, 8px); box-shadow: var(--cpq-glass-card-shadow, 0 10px 30px rgba(22,119,255,0.10));
  overflow: hidden; max-width: 100%; }
.ac-head { display: flex; align-items: center; gap: var(--cpq-space-2, 8px); width: 100%;
  padding: var(--cpq-space-2, 8px) var(--cpq-space-3, 12px); background: transparent;
  border: none; cursor: pointer; text-align: left; font-family: inherit; }
.ac-head:hover { background: var(--cpq-overlay-w4, rgba(22,119,255,0.04)); }
.ac-icon { width: 28px; height: 28px; border-radius: var(--cpq-radius-md, 6px);
  background: var(--cpq-overlay-w10, rgba(22,119,255,0.10)); display: flex;
  align-items: center; justify-content: center; font-size: 14px; flex: none; }
.ac-meta { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ac-title { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary, #1d2129); }
.ac-sub { font-size: 11px; color: var(--cpq-text-muted, #86909c); }
.ac-view { margin-left: auto; font-size: 11px; color: var(--cpq-accent-primary, #1677FF); flex: none; }
.ac-loading { font-size: 12px; color: var(--cpq-text-muted, #86909c); padding: var(--cpq-space-2, 8px) 0; }
.ac-toolbar { display: flex; align-items: center; gap: var(--cpq-space-4, 16px); margin-bottom: var(--cpq-space-3, 12px); }
.deep-link { font-size: 12px; color: var(--cpq-accent-primary, #1677FF); cursor: pointer; margin-left: auto; }
.ac-foot { display: flex; justify-content: flex-end; gap: var(--cpq-space-2, 8px); margin-top: var(--cpq-space-3, 12px); }
.share-row { display: flex; align-items: center; gap: var(--cpq-space-2, 8px); flex-wrap: wrap; }
.share-path { font-family: Consolas, monospace; font-size: 12px; background: var(--cpq-overlay-w6, rgba(22,119,255,0.08));
  border-radius: var(--cpq-radius-sm, 4px); padding: 3px 8px; word-break: break-all; }

<style>
/* 产物卡弹窗 teleport 到 body，需非 scoped：层级压过办公室聊天面板(1800)/方案助手面板(1500) */
.artifact-modal-wrap { z-index: 2000; }
.artifact-modal-full .ant-modal { max-width: 100vw; top: 0; padding-bottom: 0; }
.artifact-modal-full .ant-modal-content { border-radius: 0; min-height: 100vh; }
</style>
