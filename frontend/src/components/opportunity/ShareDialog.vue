<script setup lang="ts">
/**
 * 产出物分享弹窗（公共组件，网盘式）——四个节点的产出物统一复用。
 * 视角 = 同一模板的信息维度（scheme=无价格列 / cost=只显成本价 / customer=完整报价；
 * customer 一期锁定——等效外发，二期开放时创建须过外发审批闸）。
 * quote 走导出模板管线（Univer 只读预览）；cost/scheme 投影成同构数据走同一管线。
 */
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { artifactShareApi, type ArtifactShare, type SharePreviewResult, type ShareView } from '@/api/artifactShare'
import { univerTemplateApi } from '@/api/univerTemplate'
import { fetchAuthedBlob } from '@/utils/fileDownload'
import { downloadBlob } from '@/utils/download'
import UniverSheet from '@/components/UniverSheet.vue'
import OutboundApprovalModal from '@/components/quotation/OutboundApprovalModal.vue'
import { MODAL_BODY_MAX_HEIGHT_WITH_FOOTER } from '@/constants/modalPresets'
import ResponsiveModal from '@/components/common/ResponsiveModal.vue'

const props = withDefaults(defineProps<{
  open: boolean
  opportunityId: string
  sourceType: 'quote' | 'cost' | 'scheme'
  sourceId: string | number
  title?: string
  defaultView?: ShareView
}>(), { defaultView: 'customer', title: '' })

const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const views: Array<{ key: ShareView; label: string }> = [
  { key: 'scheme', label: '方案' },
  { key: 'cost', label: '成本' },
  { key: 'customer', label: '报价' },
]

const view = ref<ShareView>('customer')
const templateId = ref<number | undefined>(undefined)
const templates = ref<Array<{ id: number; display_name: string; is_default?: boolean }>>([])
const preview = ref<SharePreviewResult | null>(null)
const previewLoading = ref(false)
const expiryDays = ref(7)
const extractCode = ref('')
const creating = ref(false)
const downloading = ref(false)
const createdShare = ref<ArtifactShare | null>(null)
const existingShares = ref<ArtifactShare[]>([])

watch(() => props.open, async (v) => {
  if (!v) return
  hydrating = true
  view.value = props.defaultView || 'customer'
  templateId.value = undefined
  preview.value = null
  createdShare.value = null
  existingShares.value = []
  extractCode.value = ''
  expiryDays.value = 7
  try {
    const list = await univerTemplateApi.list()
    templates.value = (list || []).map(t => ({ id: t.id, display_name: t.display_name || t.name, is_default: t.is_default }))
    const def = templates.value.find(t => t.is_default)
    if (def) templateId.value = def.id
  } catch { /* 模板拉不到时仍可用默认管线 */ }
  hydrating = false
  void loadPreview()
  void loadExisting()
})

// 打开时的重置会触发 view/templateId 侦听 → hydrating 标志消重；
// 预览请求允许并发，落地只认最新序号（过期响应丢弃，转圈不会卡死）
let previewSeq = 0
let hydrating = false

watch([view, templateId], () => {
  if (props.open && !hydrating) void loadPreview()
})

async function loadPreview() {
  const seq = ++previewSeq
  previewLoading.value = true
  try {
    const res = await artifactShareApi.preview(props.opportunityId, {
      source_type: props.sourceType,
      source_id: props.sourceId,
      view: view.value,
      template_id: templateId.value,
    })
    if (seq !== previewSeq) return
    preview.value = res
  } catch (e: any) {
    if (seq !== previewSeq) return
    if (onGate409(e, () => void loadPreview())) return
    preview.value = null
    message.error(e?.response?.data?.detail || '预览失败')
  } finally {
    if (seq === previewSeq) previewLoading.value = false
  }
}

async function loadExisting() {
  try {
    const res = await artifactShareApi.list(props.opportunityId, props.sourceType, props.sourceId)
    existingShares.value = (res.shares || []).filter(s => !s.revoked_at)
  } catch { /* 列表拉不到不阻塞分享 */ }
}

async function generateLink() {
  creating.value = true
  try {
    const res = await artifactShareApi.create(props.opportunityId, {
      source_type: props.sourceType,
      source_id: props.sourceId,
      view: view.value,
      template_id: templateId.value,
      expiry_days: expiryDays.value,
      extract_code: extractCode.value.trim() || undefined,
    })
    createdShare.value = res.share
    message.success('链接已生成')
    await loadExisting()
  } catch (e: any) {
    if (onGate409(e, () => void generateLink())) return
    message.error(e?.response?.data?.detail || '生成失败')
  } finally {
    creating.value = false
  }
}

async function doDownload() {
  downloading.value = true
  try {
    const url = artifactShareApi.downloadUrl(props.opportunityId, {
      source_type: props.sourceType,
      source_id: props.sourceId,
      view: view.value,
      template_id: templateId.value,
    })
    const blob = await fetchAuthedBlob(url)
    const name = createdShare.value?.filename || `${props.title || props.sourceType}_${view.value}.xlsx`
    downloadBlob(blob, name)
  } catch (e: any) {
    if (onGate409(e, () => void doDownload())) return
    message.error(e?.response?.data?.detail || '下载失败')
  } finally {
    downloading.value = false
  }
}

async function copyLink(share: ArtifactShare) {
  const link = artifactShareApi.shareLink(share.token)
  try {
    await navigator.clipboard.writeText(link)
    message.success('链接已复制')
  } catch {
    message.info(link)
  }
}

async function revokeShare(share: ArtifactShare) {
  try {
    await artifactShareApi.revoke(props.opportunityId, share.id)
    message.success('已撤销，链接立即失效')
    createdShare.value = null
    await loadExisting()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '撤销失败')
  }
}

function fmtExpiry(s: ArtifactShare): string {
  return (s.expires_at || '').slice(0, 10)
}

// ── 外发审批闸：报价视角（quote 来源）无有效许可 → 原地弹审批发起窗，批完自动重试 ──
const gateModalOpen = ref(false)
let afterApproval: (() => void) | null = null

function onGate409(e: any, retry: () => void): boolean {
  if (e?.response?.status !== 409) return false
  afterApproval = retry
  gateModalOpen.value = true
  return true
}

function retryAfterApproval() {
  afterApproval?.()
  afterApproval = null
}
</script>

<template>
  <ResponsiveModal
    :open="open"
    :title="`分享 · ${title || sourceType}`"
    tier="sheet"
    centered
    wrap-class-name="portal-sheet-modal"
    :body-style="{ maxHeight: MODAL_BODY_MAX_HEIGHT_WITH_FOOTER, overflowY: 'auto' }"
    @cancel="emit('update:open', false)"
  >
    <div class="sd-body">
      <div class="sd-row">
        <span class="k">视角</span>
        <div class="seg">
          <span
            v-for="v in views"
            :key="v.key"
            :class="{ on: view === v.key }"
            @click="view = v.key"
          >{{ v.label }}</span>
        </div>
        <span v-if="view === 'customer' && sourceType === 'quote'" class="sd-view-warn">报价视角=报价数据出门，须持有效外发许可</span>
      </div>

      <div class="sd-row">
        <span class="k">模板</span>
        <a-select
          v-model:value="templateId"
          :options="templates.map(t => ({ label: t.display_name + (t.is_default ? ' (默认)' : ''), value: t.id }))"
          placeholder="默认模板"
          style="flex: 1"
          allow-clear
        />
      </div>

      <div class="sd-preview">
        <a-spin v-if="previewLoading" tip="渲染中…" class="sd-spin" />
        <UniverSheet
          v-else-if="preview?.workbook_snapshot"
          :workbook-data="preview.workbook_snapshot"
          :editable="false"
          class="sd-univer"
        />
        <div v-else class="sd-empty">暂无预览</div>
      </div>

      <div class="sd-row">
        <span class="k">有效期</span>
        <a-select
          v-model:value="expiryDays"
          :options="[ { label: '1 天', value: 1 }, { label: '7 天', value: 7 }, { label: '30 天', value: 30 } ]"
          style="width: 110px"
        />
        <span class="k">提取码</span>
        <a-input v-model:value="extractCode" :maxlength="8" placeholder="可选" style="width: 110px" />
      </div>

      <div v-if="createdShare" class="sd-link">
        <span class="url">{{ artifactShareApi.shareLink(createdShare.token) }}</span>
        <a-button size="small" @click="copyLink(createdShare)">⧉ 复制</a-button>
        <a-button size="small" danger @click="revokeShare(createdShare)">撤销</a-button>
      </div>

      <div v-if="existingShares.length" class="sd-history">
        <div class="sd-hist-title">此产出物的有效链接（{{ existingShares.length }}）</div>
        <div v-for="s in existingShares" :key="s.id" class="sd-hist-row">
          <span class="sd-hist-name">{{ s.filename }}<span class="muted"> · {{ s.view }}视角 · 到期 {{ fmtExpiry(s) }} · 已下载 {{ s.download_count }} 次</span></span>
          <span class="sd-hist-acts">
            <a-button size="small" @click="copyLink(s)">复制</a-button>
            <a-button size="small" danger @click="revokeShare(s)">撤销</a-button>
          </span>
        </div>
      </div>

      <div class="sd-hint">
        分享文件同时归档到商机附件桶；链接可过期/可撤销/可选提取码；每次下载记审计。报价视角=报价数据出门，quote 须持有效外发许可。
      </div>
    </div>
    <template #footer>
      <a-button @click="emit('update:open', false)">关闭</a-button>
      <a-button type="primary" :loading="downloading" @click="doDownload">下载 Excel</a-button>
      <a-button type="primary" :loading="creating" @click="generateLink">生成链接</a-button>
    </template>

    <!-- 报价视角撞外发审批闸：原地弹审批发起窗（批完自动重试刚才的动作） -->
    <OutboundApprovalModal
      v-model:open="gateModalOpen"
      :opportunity-id="opportunityId"
      :quotation-id="String(sourceId)"
      :quotation-label="title"
      @submitted="retryAfterApproval"
    />
  </ResponsiveModal>
</template>

<style scoped>
.sd-body { display: flex; flex-direction: column; gap: 12px; padding-top: 4px; }
.sd-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12.5px; }
.sd-row .k { width: 44px; flex-shrink: 0; color: var(--cpq-text-muted); }
.seg { display: inline-flex; border: 1px solid var(--cpq-border-light, rgba(255,255,255,0.15)); border-radius: var(--cpq-radius-sm); overflow: hidden; }
.seg span { padding: 3px 12px; cursor: pointer; color: var(--cpq-text-secondary); }
.seg span.on { background: var(--cpq-overlay-a10, rgba(22,119,255,0.10)); color: var(--cpq-accent-primary-light, #4096ff); font-weight: 600; }
.seg span.off { color: var(--cpq-text-muted); cursor: not-allowed; }
.sd-preview {
  height: 56vh;
  min-height: 420px;
  border: 1px solid var(--cpq-border-primary, rgba(255,255,255,0.10));
  border-radius: var(--cpq-radius-md); overflow: hidden; position: relative; background: #fff;
}
.sd-univer { height: 100%; }
.sd-spin { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); }
.sd-view-warn {
  padding: 2px 10px; border-radius: var(--cpq-radius-full); font-size: 11px;
  background: var(--cpq-notif-amber-bg, rgba(250, 173, 20, 0.18));
  color: var(--cpq-notif-amber, #F4D28A); white-space: nowrap;
}
.sd-link {
  display: flex; align-items: center; gap: 8px;
  background: var(--cpq-overlay-a8, rgba(22,119,255,0.08));
  border: 1px solid var(--cpq-overlay-a20, rgba(22,119,255,0.20));
  border-radius: var(--cpq-radius-sm); padding: 6px 10px;
}
.sd-link .url {
  flex: 1; min-width: 0; font-family: Consolas, monospace; font-size: 11.5px;
  color: var(--cpq-accent-primary-light, #4096ff);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sd-history { border-top: 1px dashed var(--cpq-border-secondary, rgba(255,255,255,0.06)); padding-top: 8px; }
.sd-hist-title { font-size: 11px; color: var(--cpq-text-muted); margin-bottom: 4px; }
.sd-hist-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; font-size: 12px; }
.sd-hist-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.muted { color: var(--cpq-text-muted); }
.sd-hist-acts { display: inline-flex; gap: 6px; flex-shrink: 0; }
.sd-hint { font-size: 11px; color: var(--cpq-text-muted); line-height: 1.7; }
</style>
