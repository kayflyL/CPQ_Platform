<template>
  <div class="archive-section glass">
    <div class="section-header">
      <h3>存档区</h3>
      <span class="section-hint">需求文档 / 方案·详细报价 / 已发报价 — 拖拽或点 + 上传到对应分类</span>
    </div>
    <div class="archive-cols">
      <div
        v-for="col in columns"
        :key="col.category"
        class="archive-col"
        :class="{ dragging: draggingCategory === col.category }"
        @dragover.prevent="draggingCategory = col.category"
        @dragleave.prevent="draggingCategory = draggingCategory === col.category ? null : draggingCategory"
        @drop.prevent="onDrop(col.category, $event)"
      >
        <div class="col-head">
          <span class="col-icon">{{ col.icon }}</span>
          <span class="col-title">{{ col.title }}</span>
          <span class="col-count">{{ items(col.category).length }}</span>
          <button class="col-upload" @click="triggerUpload(col.category)" title="上传到此分类">
            <PlusOutlined />
          </button>
        </div>
        <div class="col-body">
          <div v-if="draggingCategory === col.category" class="drop-hint">释放以上传到{{ col.title }}</div>
          <a-empty v-else-if="!items(col.category).length" :image-style="{ height: '40px' }" description="暂无" />
          <div v-else class="file-list">
            <div v-for="a in items(col.category)" :key="a.attachment_id" class="archive-file">
              <component :is="fileIcon(a.original_filename)" class="file-ic" />
              <div class="file-main" @click="download(a)">
                <div class="file-name" :title="a.original_filename">{{ a.original_filename }}</div>
                <div class="file-meta">{{ formatSize(a.file_size) }} · {{ a.uploader_name || '匿名' }} · {{ formatTime(a.created_at) }}</div>
              </div>
              <a-dropdown placement="bottomRight" :trigger="['click']">
                <button class="file-act" title="移动到其他分类"><SwapOutlined /></button>
                <template #overlay>
                  <a-menu @click="(e: any) => changeCategory(a, String(e.key))">
                    <a-menu-item v-for="col in columns" :key="col.category" :disabled="col.category === a.category">
                      {{ col.icon }} {{ col.title }}
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
              <button class="file-act" @click="download(a)" title="下载"><DownloadOutlined /></button>
              <button class="file-act danger" @click="remove(a)" title="删除"><DeleteOutlined /></button>
            </div>
          </div>
        </div>
        <input :ref="(el:any) => (fileInputs[col.category] = el)" type="file" multiple hidden @change="onFilePicked(col.category, $event)" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlusOutlined, DownloadOutlined, DeleteOutlined, SwapOutlined,
  FileExcelOutlined, FilePdfOutlined, FileImageOutlined, FileOutlined,
} from '@ant-design/icons-vue'
import { feedApi } from '@/api/feed'
import type { FeedAttachment } from '@/api/feed'

const props = defineProps<{ opportunityId: string; attachments: FeedAttachment[] }>()

const columns = [
  { category: 'requirement', title: '需求文档', icon: '📋' },
  { category: 'technical', title: '方案/详细报价', icon: '🔧' },
  { category: 'sent_quote', title: '已发报价', icon: '📤' },
] as const

const draggingCategory = ref<string | null>(null)
const fileInputs = reactive<Record<string, HTMLInputElement | null>>({})

const items = (category: string) => (props.attachments || []).filter((a) => a.category === category)

async function uploadFiles(category: string, files: File[]) {
  if (!files.length) return
  let ok = 0
  let fail = 0
  for (const f of files) {
    try {
      await feedApi.attachments.upload(props.opportunityId, f, { category })
      ok++
    } catch {
      fail++
    }
  }
  if (ok) message.success(`已上传 ${ok} 个文件`)
  if (fail) message.error(`${fail} 个文件上传失败`)
}

function triggerUpload(category: string) {
  fileInputs[category]?.click()
}
function onFilePicked(category: string, e: Event) {
  const target = e.target as HTMLInputElement
  uploadFiles(category, Array.from(target.files || []))
  target.value = ''
}
function onDrop(category: string, e: DragEvent) {
  draggingCategory.value = null
  uploadFiles(category, Array.from(e.dataTransfer?.files || []))
}

async function remove(a: FeedAttachment) {
  try {
    await feedApi.attachments.remove(a.attachment_id)
    message.success('已删除')
  } catch {
    message.error('删除失败')
  }
}
async function changeCategory(a: FeedAttachment, category: string) {
  if (category === a.category) return
  try {
    await feedApi.attachments.updateCategory(a.attachment_id, category)
    // WS 广播回推 upsert,本地列表自动挪栏
  } catch {
    message.error('移动失败')
  }
}
function download(a: FeedAttachment) {
  window.open(feedApi.attachments.downloadUrl(a.attachment_id), '_blank')
}

function fileIcon(name: string) {
  const ext = name.toLowerCase().split('.').pop() || ''
  if (['xlsx', 'xls', 'csv'].includes(ext)) return FileExcelOutlined
  if (ext === 'pdf') return FilePdfOutlined
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return FileImageOutlined
  return FileOutlined
}
function formatSize(bytes: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}
function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>

<style scoped>
.archive-section {
  padding: 16px 20px;
  margin-bottom: 24px;
}
.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.section-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.archive-cols {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.archive-col {
  background: var(--cpq-glass-2-bg);
  border: 1px solid var(--cpq-glass-border);
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 160px;
  transition: all var(--cpq-transition-fast);
}
.archive-col.dragging {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a5);
  box-shadow: inset 0 0 20px var(--cpq-overlay-a8);
}
.col-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
}
.col-icon { font-size: 14px; }
.col-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); flex: 1; }
.col-count {
  font-size: 11px; color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w6); padding: 1px 7px; border-radius: 10px;
}
.col-upload {
  width: 22px; height: 22px; border-radius: 6px; border: none;
  background: var(--cpq-overlay-a8); color: var(--cpq-accent-primary);
  cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px;
}
.col-upload:hover { background: var(--cpq-overlay-a20); }
.col-body { flex: 1; position: relative; }
.drop-hint {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: var(--cpq-accent-primary); font-weight: 600; font-size: 13px;
  background: var(--cpq-overlay-a5); border-radius: 8px;
}
.file-list { display: flex; flex-direction: column; gap: 6px; }
.archive-file {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; background: var(--cpq-overlay-w3);
  border: 1px solid var(--cpq-overlay-w6); border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}
.archive-file:hover { border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-a4); }
.file-ic { font-size: 18px; flex-shrink: 0; }
.file-main { flex: 1; min-width: 0; cursor: pointer; }
.file-name {
  font-size: 12px; font-weight: 500; color: var(--cpq-text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.file-meta { font-size: 10px; color: var(--cpq-text-muted); margin-top: 1px; }
.file-act {
  width: 22px; height: 22px; border-radius: 5px; border: none;
  background: transparent; color: var(--cpq-text-muted); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; font-size: 12px;
  opacity: 0; transition: all var(--cpq-transition-fast);
}
.archive-file:hover .file-act { opacity: 1; }
.file-act:hover { background: var(--cpq-overlay-w6); color: var(--cpq-text-primary); }
.file-act.danger:hover { background: var(--cpq-overlay-danger10); color: var(--cpq-accent-danger); }
</style>
