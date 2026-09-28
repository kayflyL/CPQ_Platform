<template>
  <a-modal
    :open="open"
    :title="attachment?.original_filename || '预览'"
    :footer="null"
    width="92vw"
    wrap-class-name="att-preview-wrap"
    :destroy-on-close="true"
    @update:open="(v: boolean) => $emit('update:open', v)"
  >
    <div class="preview-body">
      <a-spin v-if="loading" tip="加载中…" class="preview-spin" />

      <!-- image -->
      <div v-else-if="kind === 'image'" class="preview-center">
        <img :src="url" :alt="attachment?.original_filename" class="preview-img" />
      </div>

      <!-- pdf (native viewer via iframe) -->
      <iframe v-else-if="kind === 'pdf'" :src="url" class="preview-iframe" title="pdf"></iframe>

      <!-- excel: in-browser Univer editor -->
      <div v-else-if="kind === 'excel'" class="excel-wrap">
        <div class="excel-toolbar">
          <span class="excel-hint">在线编辑 · 保存会作为新版本（保留历史）</span>
          <a-space>
            <a-button :loading="saving" @click="download">下载当前版本</a-button>
            <a-button type="primary" :loading="saving" :disabled="!snapshot" @click="saveVersion">保存为新版本</a-button>
          </a-space>
        </div>
        <div class="excel-canvas">
          <UniverSheet v-if="snapshot" ref="univerRef" :workbook-data="snapshot" :editable="true" />
        </div>
      </div>

      <!-- unsupported -->
      <div v-else-if="kind === 'other'" class="preview-center unsupported">
        <FileOutlined style="font-size: 40px; color: var(--cpq-text-muted)" />
        <p>此类型暂不支持在线预览，请下载查看</p>
        <a-button type="primary" @click="download">下载</a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch, defineAsyncComponent } from 'vue'
import { FileOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
// Univer 体积巨大（dev 预打包 33MB / prod chunk 10MB），只在真正预览 Excel 时才拉，
// 避免挂进商机详情页首屏关键路径（曾导致进详情页先卡数十秒）
const UniverSheet = defineAsyncComponent(() => import('@/components/UniverSheet.vue'))
import { feedApi } from '@/api/feed'
import type { FeedAttachment } from '@/api/feed'
import { univerTemplateApi } from '@/api/univerTemplate'
import { fetchAuthedBlob, downloadOfficeFile, previewOfficeFileUrl } from '@/utils/fileDownload'

const props = defineProps<{ attachment: FeedAttachment | null; open: boolean }>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'saved', att: FeedAttachment): void
}>()

const loading = ref(false)
const saving = ref(false)
const snapshot = ref<Record<string, any> | null>(null)
const univerRef = ref<InstanceType<typeof UniverSheet> | null>(null)

// 下载端点挂了 current_user 鉴权，img/iframe/fetch 直链都会 401：
// 统一走带 Authorization 的 blob 拉取；image/pdf 用 objectURL 展示
const rawUrl = computed(() => (props.attachment ? feedApi.attachments.downloadUrl(props.attachment.attachment_id) : ''))
const url = ref('')

function revokeUrl() {
  if (url.value) {
    URL.revokeObjectURL(url.value)
    url.value = ''
  }
}

function extOf(name: string): string {
  return (name.toLowerCase().split('.').pop() || '').trim()
}
const kind = computed<'image' | 'pdf' | 'excel' | 'other'>(() => {
  const e = extOf(props.attachment?.original_filename || '')
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(e)) return 'image'
  if (e === 'pdf') return 'pdf'
  if (['xlsx', 'xls', 'csv'].includes(e)) return 'excel'
  return 'other'
})

async function loadExcel() {
  if (!props.attachment) return
  loading.value = true
  snapshot.value = null
  try {
    const blob = await fetchAuthedBlob(rawUrl.value)
    const file = new File([blob], props.attachment.original_filename, {
      type: props.attachment.mime_type || 'application/vnd.ms-excel',
    })
    const result = await univerTemplateApi.uploadExcel(file)
    snapshot.value = result.workbook_snapshot
  } catch (e) {
    console.error('加载 Excel 失败', e)
    message.error('加载 Excel 失败，请下载查看')
  } finally {
    loading.value = false
  }
}

async function saveVersion() {
  if (!props.attachment || !univerRef.value) return
  saving.value = true
  try {
    const resolved = univerRef.value.getResolvedWorkbook()
    const { resolvedWorkbookToXlsx } = await import('@/utils/xlsx-exporter')
    const blob = await resolvedWorkbookToXlsx(resolved)
    const file = new File([blob], props.attachment.original_filename, {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const att = await feedApi.attachments.addVersion(props.attachment.attachment_id, file)
    message.success('已保存为新版本')
    emit('saved', att)
    emit('update:open', false)
  } catch (e) {
    console.error('保存失败', e)
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function download() {
  if (props.attachment) {
    try {
      await downloadOfficeFile(rawUrl.value, props.attachment.original_filename)
    } catch {
      message.error('下载失败')
    }
  }
}

// when opening a new attachment, reset + load excel snapshot / objectURL
watch(
  () => [props.open, props.attachment?.attachment_id],
  async ([isOpen]) => {
    revokeUrl()
    snapshot.value = null
    if (isOpen && kind.value === 'excel') {
      await loadExcel()
    } else if (isOpen && (kind.value === 'image' || kind.value === 'pdf')) {
      loading.value = true
      try {
        url.value = await previewOfficeFileUrl(rawUrl.value)
      } catch (e) {
        console.error('加载预览失败', e)
        message.error('加载失败，请下载查看')
      } finally {
        loading.value = false
      }
    }
  },
)
</script>

<style scoped>
.preview-body {
  height: 78vh;
  display: flex;
  flex-direction: column;
  background: var(--cpq-bg-secondary, #fff);
}
.preview-spin {
  align-self: center;
  margin-top: 40px;
}
.preview-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  overflow: auto;
}
.preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.preview-iframe {
  flex: 1;
  width: 100%;
  border: none;
  min-height: 70vh;
}
.unsupported {
  color: var(--cpq-text-muted);
}
.excel-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.excel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px;
}
.excel-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.excel-canvas {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--cpq-overlay-w6, #eee);
  border-radius: 6px;
  overflow: hidden;
}
</style>

<style>
/* Univer inside a modal needs the container to fill height */
.att-preview-wrap .ant-modal-body {
  padding: 12px;
}
</style>
