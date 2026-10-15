<script setup lang="ts">
/**
 * 需求附件徽标条（需求单弹窗内嵌，宿主=OpportunityProcessBoard 需求单 modal）。
 * 上传/预览/删除随单完成，附件钉到需求单版本（requirement_version），提交后随版本快照留档。
 *
 * 过滤：category=lead_requirement 且（requirement_version=当前版本 或 NULL=未归版散件，降级合并显示）。
 * 溢出=换行不横向滑动（滑动藏件名，违背"挂了什么一眼可扫"）；手机端无 hover，点徽标开预览看全名。
 */
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { feedApi } from '@/api/feed'
import type { FeedAttachment } from '@/api/feed'

const props = withDefaults(defineProps<{
  opportunityId: string
  /** 绑定的需求单版本；null=新建草稿尚未落库（上传仍可用，落为未归版散件，存草稿后新上传才钉版本） */
  version: number | null
  attachments: FeedAttachment[]
  readonly?: boolean
}>(), { readonly: false })

const emit = defineEmits<{
  (e: 'preview', a: FeedAttachment): void
}>()

const uploading = ref(false)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const ACCEPT = '.xlsx,.xls,.pdf,.doc,.docx,.png,.jpg,.jpeg'
const LEAD_CATEGORY = 'lead_requirement'

const visibleAtts = computed(() =>
  (props.attachments || []).filter(a =>
    a.category === LEAD_CATEGORY &&
    !a.deleted_at &&
    (a.requirement_version == null || a.requirement_version === props.version)))

function kindOf(name: string): 'xls' | 'pdf' | 'img' | 'doc' | 'file' {
  const e = (name.toLowerCase().split('.').pop() || '').trim()
  if (['xlsx', 'xls', 'csv'].includes(e)) return 'xls'
  if (e === 'pdf') return 'pdf'
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(e)) return 'img'
  if (['doc', 'docx'].includes(e)) return 'doc'
  return 'file'
}

const KIND_LABEL: Record<string, string> = { xls: 'XLS', pdf: 'PDF', img: 'IMG', doc: 'DOC', file: 'FILE' }

function metaText(a: FeedAttachment): string {
  const size = a.file_size >= 1024 * 1024
    ? `${(a.file_size / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(a.file_size / 1024))} KB`
  return `${a.original_filename} · ${size}${a.uploader_name ? ` · ${a.uploader_name}` : ''} · ${(a.created_at || '').slice(5, 16)}`
}

async function uploadFiles(files: File[]) {
  if (!files.length || props.readonly) return
  uploading.value = true
  let ok = 0
  let fail = 0
  for (const f of files) {
    try {
      await feedApi.attachments.upload(props.opportunityId, f, {
        category: LEAD_CATEGORY,
        requirement_version: props.version,
      })
      ok++
    } catch {
      fail++
    }
  }
  uploading.value = false
  if (ok) message.success(`已上传 ${ok} 个文件${props.version ? `，钉在需求单 v${props.version}` : ''}`)
  if (fail) message.error(`${fail} 个文件上传失败`)
}

function onPicked(clickEvent: Event) {
  const target = clickEvent.target as HTMLInputElement
  const files = Array.from(target.files || [])
  target.value = ''
  void uploadFiles(files)
}

function onDrop(e: DragEvent) {
  dragging.value = false
  if (props.readonly) return
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) void uploadFiles(files)
}

function onDragLeave(e: DragEvent) {
  if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) dragging.value = false
}

async function removeAtt(a: FeedAttachment) {
  try {
    await feedApi.attachments.remove(a.attachment_id)
  } catch {
    message.error('删除失败')
  }
}

defineExpose({ uploadFiles })
</script>

<template>
  <section
    v-if="!readonly || visibleAtts.length"
    class="rac"
    :class="{ readonly, dragging }"
    @dragover.prevent="dragging = true"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <h4 class="rac-title">
      需求附件
      <span class="rac-hint">
        <template v-if="readonly">随本版需求单留档 · 点徽标预览</template>
        <template v-else>点徽标预览 · 拖拽文件到本区，或在需求原文里 Ctrl+V 粘贴截图</template>
      </span>
    </h4>

    <div class="chip-strip">
      <span
        v-for="a in visibleAtts"
        :key="a.attachment_id"
        class="rac-chip"
        :title="metaText(a)"
        @click="emit('preview', a)"
      >
        <i class="rac-badge" :class="kindOf(a.original_filename)">{{ KIND_LABEL[kindOf(a.original_filename)] }}</i>
        <span class="rac-name">{{ a.original_filename }}</span>
        <a-popconfirm
          v-if="!readonly"
          title="从本需求单删除该附件？文件将从归档中移除"
          ok-text="删除"
          cancel-text="取消"
          @confirm="removeAtt(a)"
        >
          <span class="rac-x" @click.stop>✕</span>
        </a-popconfirm>
      </span>

      <button v-if="!readonly" type="button" class="rac-chip rac-add" @click="fileInput?.click()">＋ 上传</button>
      <span v-if="uploading" class="rac-uploading">上传中…</span>
    </div>

    <input ref="fileInput" type="file" multiple hidden :accept="ACCEPT" @change="onPicked" />
  </section>
</template>

<style scoped>
.rac {
  margin-bottom: var(--cpq-space-5, 24px);
  border-radius: var(--cpq-radius-md, 12px);
  padding: var(--cpq-space-3, 12px) var(--cpq-space-4, 16px);
  border: 1px dashed transparent;
  transition: border-color 0.2s, background 0.2s;
}
.rac.dragging {
  border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.08));
}
.rac-title {
  margin: 0 0 var(--cpq-space-2, 8px);
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-secondary, #9ba1aa);
}
.rac-hint {
  margin-left: var(--cpq-space-2, 8px);
  font-size: 11px;
  font-weight: 400;
  color: var(--cpq-text-muted, #6e7582);
}
.chip-strip {
  display: flex;
  flex-wrap: wrap;
  gap: var(--cpq-space-2, 8px);
  align-items: center;
}
.rac-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: min(240px, 62vw);
  padding: 3px var(--cpq-space-2, 8px);
  border-radius: 999px;
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.04));
  border: 1px solid var(--cpq-border-light, rgba(255, 255, 255, 0.15));
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.rac-chip:hover {
  border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.06));
}
.rac-badge {
  font-style: normal;
  flex-shrink: 0;
  width: 20px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 8px;
  font-weight: 700;
  border-radius: var(--cpq-space-1, 4px);
}
.rac-badge.xls { background: var(--cpq-notif-green-bg, rgba(82, 201, 160, 0.18)); color: var(--cpq-notif-green, #52C9A0); }
.rac-badge.pdf { background: var(--cpq-notif-red-bg, rgba(255, 107, 107, 0.16)); color: var(--cpq-notif-red, #FF6B6B); }
.rac-badge.img { background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.10)); color: var(--cpq-accent-primary-light, #4096ff); }
.rac-badge.doc, .rac-badge.file { background: var(--cpq-overlay-w8, rgba(255, 255, 255, 0.08)); color: var(--cpq-text-secondary, #9ba1aa); }
.rac-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--cpq-text-primary, #e8ecef);
}
.rac-x {
  flex-shrink: 0;
  color: var(--cpq-text-muted, #6e7582);
  font-size: 11px;
  padding: 0 2px;
}
.rac-x:hover { color: var(--cpq-accent-danger, #ff6b6b); }
.rac-chip.rac-add {
  border-style: dashed;
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.08));
  color: var(--cpq-accent-primary-light, #4096ff);
  font-weight: 600;
}
.rac-chip.rac-add:hover { background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.10)); }
.rac-uploading {
  font-size: var(--cpq-font-size-sm, 12px);
  color: var(--cpq-text-muted, #6e7582);
}
</style>
