<template>
  <div class="archive-section glass">
    <div class="section-header">
      <h3>存档区</h3>
      <span class="section-hint">{{ sectionHint }}</span>
    </div>

    <div class="archive-toolbar">
      <a-input v-model:value="searchText" placeholder="搜索文件名 / 上传人" allow-clear class="toolbar-search">
        <template #prefix><SearchOutlined /></template>
      </a-input>
      <a-select v-model:value="typeFilter" :options="TYPE_OPTIONS" class="toolbar-select" />
      <a-select v-model:value="sortBy" :options="SORT_OPTIONS" class="toolbar-select" />
      <div class="view-toggle">
        <button type="button" :class="{ on: viewMode === 'grid' }" title="三栏视图" @click="viewMode = 'grid'"><AppstoreOutlined /></button>
        <button type="button" :class="{ on: viewMode === 'list' }" title="列表视图" @click="viewMode = 'list'"><UnorderedListOutlined /></button>
      </div>
    </div>

    <div v-if="viewMode === 'grid'" class="archive-cols">
      <div
        v-for="col in columns"
        :key="col.category"
        class="archive-col"
        :class="{ dragging: draggingCategory === col.category }"
        @dragenter.prevent="onDragEnter(col.category)"
        @dragover.prevent
        @dragleave.prevent="onDragLeave(col.category)"
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
              <div class="file-main" @click="$emit('preview', a)">
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

    <div v-else class="archive-list">
      <!-- 列表视图：扁平表格，统一搜索/筛选/排序，复用同一套预览/移动/下载/删除 -->
      <a-table
        :data-source="sortedFiltered"
        :columns="listColumns"
        :pagination="false"
        size="small"
        row-key="attachment_id"
        :locale="{ emptyText: '没有符合条件的文件' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <div class="list-file-name" @click="$emit('preview', record)">
              <component :is="fileIcon(record.original_filename)" class="file-ic" />
              <span class="list-file-text">{{ record.original_filename }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'category'">
            <span class="list-cat">{{ categoryLabel(record.category) }}</span>
          </template>
          <template v-else-if="column.key === 'size'">{{ formatSize(record.file_size) }}</template>
          <template v-else-if="column.key === 'uploader'">{{ record.uploader_name || '匿名' }}</template>
          <template v-else-if="column.key === 'time'">{{ formatTime(record.created_at) }}</template>
          <template v-else-if="column.key === 'action'">
            <a-space :size="0">
              <a-dropdown placement="bottomRight" :trigger="['click']">
                <button class="file-act list-act" title="移动到其他分类"><SwapOutlined /></button>
                <template #overlay>
                  <a-menu @click="(e: any) => changeCategory(record, String(e.key))">
                    <a-menu-item v-for="col in columns" :key="col.category" :disabled="col.category === record.category">
                      {{ col.icon }} {{ col.title }}
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
              <button class="file-act list-act" @click="download(record)" title="下载"><DownloadOutlined /></button>
              <button class="file-act list-act danger" @click="remove(record)" title="删除"><DeleteOutlined /></button>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlusOutlined, DownloadOutlined, DeleteOutlined, SwapOutlined,
  FileExcelOutlined, FilePdfOutlined, FileImageOutlined, FileOutlined,
  SearchOutlined, AppstoreOutlined, UnorderedListOutlined,
} from '@ant-design/icons-vue'
import { feedApi } from '@/api/feed'
import type { FeedAttachment } from '@/api/feed'
import { downloadOfficeFile } from '@/utils/fileDownload'
import { useAuthStore } from '@/store/auth'

const props = defineProps<{ opportunityId: string; attachments: FeedAttachment[]; categories?: string[] }>()
const emit = defineEmits<{
  (e: 'preview', a: FeedAttachment): void
  (e: 'delete', a: FeedAttachment): void
}>()

const auth = useAuthStore()

const ALL_COLUMNS = [
  { category: 'requirement', title: '成本附件', icon: '📋' },
  { category: 'technical', title: '方案附件', icon: '📦' },
  { category: 'sent_quote', title: '报价附件', icon: '📤' },
  { category: 'lead_requirement', title: '我的附件', icon: '📎' },
] as const

// 受限列需对应权限（与后端 _CATEGORY_VIEW_PERM 同步）
const CATEGORY_PERM: Record<string, string> = {
  requirement: 'field.flow.cost',
  technical: 'field.flow.bom',
}

const columns = computed(() => {
  const visible = ALL_COLUMNS.filter((c) => !CATEGORY_PERM[c.category] || auth.can(CATEGORY_PERM[c.category]))
  if (props.categories && props.categories.length) {
    const set = new Set(props.categories)
    return visible.filter((c) => set.has(c.category))
  }
  return visible
})

const sectionHint = computed(() => {
  if (props.categories && props.categories.length === 1 && props.categories[0] === 'lead_requirement') {
    return '上传或拖拽文件到“我的附件”'
  }
  return `${columns.value.map(c => c.title).join(' / ')} — 拖拽或点 + 上传到对应分类`
})

const draggingCategory = ref<string | null>(null)
// 拖入/拖出计数器：分类列内的子元素会让浏览器在父容器上误触发 dragleave，
// 用计数器抵消，只有真正离开整列才清高亮（解决拖入时蓝色一闪一闪）
const dragCounters = reactive<Record<string, number>>({})
const fileInputs = reactive<Record<string, HTMLInputElement | null>>({})

// ── 搜索 / 筛选 / 排序 / 视图（纯前端，作用于 feed 附件列表）──
const searchText = ref('')
const typeFilter = ref<'all' | 'excel' | 'pdf' | 'image' | 'other'>('all')
const sortBy = ref<'time_desc' | 'time_asc' | 'name_asc' | 'size_desc'>('time_desc')
const viewMode = ref<'grid' | 'list'>('grid')

const TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
  { value: 'image', label: '图片' },
  { value: 'other', label: '其他' },
]
const SORT_OPTIONS = [
  { value: 'time_desc', label: '最新上传' },
  { value: 'time_asc', label: '最早上传' },
  { value: 'name_asc', label: '文件名 A-Z' },
  { value: 'size_desc', label: '文件大小' },
]
const listColumns = [
  { title: '文件名', dataIndex: 'original_filename', key: 'name' },
  { title: '分类', dataIndex: 'category', key: 'category', width: 130 },
  { title: '大小', dataIndex: 'file_size', key: 'size', width: 90 },
  { title: '上传人', dataIndex: 'uploader_name', key: 'uploader', width: 110 },
  { title: '时间', dataIndex: 'created_at', key: 'time', width: 90 },
  { title: '操作', key: 'action', width: 130 },
]

function categoryLabel(category: string) {
  return columns.value.find((c) => c.category === category)?.title || category
}
const sortedFiltered = computed(() => {
  const q = searchText.value.trim().toLowerCase()
  const list = (props.attachments || []).filter((a) => {
    if (typeFilter.value !== 'all' && fileTypeOf(a.original_filename) !== typeFilter.value) return false
    if (!q) return true
    return (a.original_filename || '').toLowerCase().includes(q)
      || (a.uploader_name || '').toLowerCase().includes(q)
  })
  const dir = sortBy.value === 'time_asc' ? 1 : -1
  return list.slice().sort((x, y) => {
    if (sortBy.value === 'name_asc') return (x.original_filename || '').localeCompare(y.original_filename || '', 'zh')
    if (sortBy.value === 'size_desc') return (y.file_size || 0) - (x.file_size || 0)
    return (new Date(x.created_at || 0).getTime() - new Date(y.created_at || 0).getTime()) * dir
  })
})
const items = (category: string) => sortedFiltered.value.filter((a) => a.category === category)

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
function onDragEnter(category: string) {
  dragCounters[category] = (dragCounters[category] || 0) + 1
  draggingCategory.value = category
}
function onDragLeave(category: string) {
  const c = Math.max(0, (dragCounters[category] || 0) - 1)
  dragCounters[category] = c
  if (c === 0 && draggingCategory.value === category) draggingCategory.value = null
}
function onDrop(category: string, e: DragEvent) {
  for (const k of Object.keys(dragCounters)) dragCounters[k] = 0
  draggingCategory.value = null
  uploadFiles(category, Array.from(e.dataTransfer?.files || []))
}

// 兜底：拦截整页文件拖放的浏览器默认行为（打开/下载文件），
// 确保松手落空或落在分类列之外时绝不触发下载——只有分类列的 drop 才真正上传
function isFileDrag(e: DragEvent) {
  return !!e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')
}
function onWindowDragOver(e: DragEvent) {
  if (isFileDrag(e)) e.preventDefault()
}
function onWindowDrop(e: DragEvent) {
  if (!isFileDrag(e)) return
  e.preventDefault()
  // 落到分类列之外：清掉残留高亮（落在列内时由上面的 onDrop 处理上传）
  for (const k of Object.keys(dragCounters)) dragCounters[k] = 0
  draggingCategory.value = null
}
onMounted(() => {
  window.addEventListener('dragover', onWindowDragOver)
  window.addEventListener('drop', onWindowDrop)
})
onBeforeUnmount(() => {
  window.removeEventListener('dragover', onWindowDragOver)
  window.removeEventListener('drop', onWindowDrop)
})

async function remove(a: FeedAttachment) {
  // 通过 emit 让父组件调用 useFeedSocket.deleteAttachment
  // 这样既有乐观更新，又有 WebSocket 广播的双重保障
  emit('delete', a)
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
async function download(a: FeedAttachment) {
  // 下载端点需鉴权，window.open 直链 401 → 走带 Authorization 的 blob 下载
  try {
    await downloadOfficeFile(feedApi.attachments.downloadUrl(a.attachment_id), a.original_filename)
  } catch {
    message.error('下载失败')
  }
}

function fileTypeOf(name: string): 'excel' | 'pdf' | 'image' | 'other' {
  const ext = (name || '').toLowerCase().split('.').pop() || ''
  if (['xlsx', 'xls', 'csv'].includes(ext)) return 'excel'
  if (ext === 'pdf') return 'pdf'
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return 'image'
  return 'other'
}
function fileIcon(name: string) {
  const t = fileTypeOf(name)
  if (t === 'excel') return FileExcelOutlined
  if (t === 'pdf') return FilePdfOutlined
  if (t === 'image') return FileImageOutlined
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
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  border: 1px solid var(--cpq-glass-border);
  border-radius: 12px;
  box-shadow: var(--cpq-glass-card-shadow);
  padding: 12px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 240px;
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
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  line-height: 1.35;
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
.archive-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.toolbar-search { width: 220px; }
.toolbar-select { width: 120px; }
.view-toggle {
  display: inline-flex;
  gap: 4px;
  margin-left: auto;
  background: var(--cpq-overlay-w3);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 8px;
  padding: 2px;
}
.view-toggle button {
  width: 28px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  font-size: 14px;
  transition: all var(--cpq-transition-fast);
}
.view-toggle button.on { background: var(--cpq-accent-primary); color: #fff; }
.archive-list { padding: 4px 0; }
.list-file-name { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; min-width: 0; }
.list-file-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.list-cat { color: var(--cpq-text-secondary); }
.list-act { opacity: 1; }
</style>
