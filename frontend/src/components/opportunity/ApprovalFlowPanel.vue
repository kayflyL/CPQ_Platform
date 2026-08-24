<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { FeedMessage } from '@/api/feed'
import type { FlowCard, FlowNode } from '@/api/portal'
import { useFeedSocket } from '@/composables/useFeedSocket'
import { feedApi } from '@/api/feed'
import { fmtTime } from '@/utils/quoteCommon'

const props = defineProps<{
  opportunityId: string
  nodes: FlowNode[]
  currentNode: string
  flowCards?: FlowCard[]
}>()

const NODE_DEFS = [
  { key: 'requirement', title: '线索登记', label: '业务' },
  { key: 'boming', title: '方案配置', label: '技术支持' },
  { key: 'costing', title: '成本核算', label: '成本核算' },
  { key: 'quoting', title: '报价单', label: '市场报价' },
]

const NODE_ORDER = NODE_DEFS.map((n) => n.key)
const NODE_LABELS: Record<string, string> = {
  requirement: '需求单',
  boming: '方案配置',
  costing: '成本核算',
  quoting: '报价单',
}

const expandedKey = ref<string>(props.currentNode || 'requirement')
const draft = ref('')
const sending = ref(false)
const selectedFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const opportunityIdRef = computed(() => props.opportunityId)
const feed = useFeedSocket(opportunityIdRef)
const { messages } = feed

watch(
  () => props.currentNode,
  (key) => {
    if (key) expandedKey.value = key
  },
)

function msgNodeKey(m: FeedMessage): string {
  return m.node_key || 'requirement'
}

function commentsFor(nodeKey: string): FeedMessage[] {
  return messages.value
    .filter((m) => m.kind === 'comment' && (m.body || m.attachments?.length) && msgNodeKey(m) === nodeKey)
    .sort((a, b) => (a.created_at < b.created_at ? -1 : 1))
}

function eventsFor(nodeKey: string): FlowNode[] {
  return props.nodes
    .filter((n) => n.node_key === nodeKey)
    .sort((a, b) => Number(a.id || 0) - Number(b.id || 0))
}

function latestEvent(nodeKey: string): FlowNode | undefined {
  const list = eventsFor(nodeKey)
  return list[list.length - 1]
}

function actionText(node: FlowNode): string {
  const label = NODE_LABELS[node.node_key] || node.node_label || node.node_key
  const version = node.version_tag ? ` ${node.version_tag}` : ''
  if (node.action === 'draft') return `生成${label}草稿`
  if (node.action === 'submit') return `提交${label}${version}`
  if (node.action === 'complete') return `完成${label}${version}`
  if (node.action === 'assign') return `开始处理${label}`
  if (node.action === 'return') return `退回${label}${version}`
  return node.node_label || node.action
}

function nodeState(nodeKey: string): 'done' | 'current' | 'pending' {
  const latest = latestEvent(nodeKey)
  if (latest && (latest.action === 'submit' || latest.action === 'complete')) return 'done'
  if (nodeKey === props.currentNode) return 'current'
  const idx = NODE_ORDER.indexOf(nodeKey)
  const curIdx = NODE_ORDER.indexOf(props.currentNode || 'requirement')
  return curIdx > idx ? 'done' : 'pending'
}

function stateText(state: string): string {
  return state === 'done' ? '已完成' : state === 'current' ? '处理中' : '待处理'
}

function toggle(nodeKey: string) {
  expandedKey.value = expandedKey.value === nodeKey ? '' : nodeKey
}

async function activate() {
  if (!props.opportunityId) return
  try {
    await feed.load()
  } catch (e: any) {
    console.error('加载评论失败:', e)
  }
  feed.connect()
}

function chooseFiles() { fileInput.value?.click() }
function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  selectedFiles.value = Array.from(input.files || [])
  input.value = ''
}
function removeSelectedFile(index: number) {
  selectedFiles.value.splice(index, 1)
}
async function postComment(nodeKey: string) {
  const body = draft.value.trim()
  if (!body && !selectedFiles.value.length) return
  sending.value = true
  try {
    await feed.postMessage(body, selectedFiles.value, nodeKey, cardIdForNode(nodeKey))
    draft.value = ''
    selectedFiles.value = []
  } catch (e: any) {
    message.error(e.response?.data?.detail || '评论发送失败')
  } finally {
    sending.value = false
  }
}

function cardIdForNode(nodeKey: string): number | null {
  const card = (props.flowCards || []).find(
    (c) => c.current_node === nodeKey && ['submitted', 'processing', 'returned'].includes(c.flow_status),
  )
  return card?.id ?? null
}

onMounted(activate)
watch(() => props.opportunityId, activate)
onBeforeUnmount(() => feed.disconnect())
</script>

<template>
  <div class="approval-flow">
    <input ref="fileInput" type="file" multiple class="af-file-input" @change="onFilesPicked" />
    <div v-for="(node, idx) in NODE_DEFS" :key="node.key" class="af-node" :class="[nodeState(node.key), { expanded: expandedKey === node.key }]">
      <button type="button" class="af-head" @click="toggle(node.key)">
        <span class="af-dot">{{ nodeState(node.key) === 'done' ? '✓' : nodeState(node.key) === 'current' ? '→' : '·' }}</span>
        <span class="af-title">
          <b>{{ String(idx + 1).padStart(2, '0') }} · {{ node.title }}</b>
          <small>{{ node.label }} · {{ stateText(nodeState(node.key)) }}</small>
        </span>
        <span class="af-latest">
          <template v-if="latestEvent(node.key)">
            {{ latestEvent(node.key)?.actor || '系统' }} · {{ fmtTime(latestEvent(node.key)?.created_at) }}
          </template>
          <template v-else>暂无流转记录</template>
        </span>
      </button>

      <div v-if="expandedKey === node.key" class="af-body">
        <div v-if="eventsFor(node.key).length" class="af-events">
          <div v-for="(ev, i) in eventsFor(node.key)" :key="ev.id ?? i" class="af-event">
            <span class="af-event-dot" />
            <span class="af-event-text">
              <b>{{ ev.actor || '系统' }} · {{ fmtTime(ev.created_at) }}</b>
              <br>
              <span>{{ actionText(ev) }}{{ ev.comment ? `：${ev.comment}` : '' }}</span>
            </span>
          </div>
        </div>

        <div class="af-comments">
          <div class="af-comment-title">节点评论</div>
          <div v-if="!commentsFor(node.key).length" class="af-comment-empty">暂无评论</div>
          <div v-for="m in commentsFor(node.key)" :key="m.message_id" class="af-comment">
            <span class="af-comment-author">{{ m.author_name || '匿名' }}</span>
            <span class="af-comment-time">{{ fmtTime(m.created_at) }}</span>
            <p>{{ m.body }}</p>
            <div v-if="m.attachments?.length" class="af-comment-files">
              <a
                v-for="att in m.attachments"
                :key="att.attachment_id"
                :href="feedApi.attachments.downloadUrl(att.attachment_id)"
                target="_blank"
                rel="noopener"
              >📎 {{ att.original_filename }}</a>
            </div>
          </div>

          <div class="af-composer">
            <a-textarea
              v-model:value="draft"
              :placeholder="`回复${node.title}`"
              :auto-size="{ minRows: 1, maxRows: 3 }"
              :disabled="sending"
              @press-enter="(e: KeyboardEvent) => { if (!e.shiftKey) { e.preventDefault(); postComment(node.key) } }"
            />
            <div class="af-composer-side">
              <a-button size="small" :disabled="sending" @click="chooseFiles">附件</a-button>
              <a-button type="primary" size="small" :loading="sending" :disabled="!draft.trim() && !selectedFiles.length" @click="postComment(node.key)">
                回复
              </a-button>
            </div>
          </div>
          <div v-if="selectedFiles.length" class="af-file-chips">
            <span v-for="(f, i) in selectedFiles" :key="`${f.name}-${i}`" class="af-file-chip">
              📎 {{ f.name }}
              <button type="button" class="af-file-remove" @click="removeSelectedFile(i)">×</button>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.approval-flow {
  display: flex;
  flex-direction: column;
}
.af-node {
  border-bottom: 1px solid var(--cpq-overlay-w5);
}
.af-node:last-child {
  border-bottom: 0;
}
.af-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}
.af-head:hover {
  background: var(--cpq-overlay-w3);
}
.af-dot {
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 11px;
  background: var(--cpq-accent-primary);
}
.af-node.done .af-dot {
  background: var(--cpq-color-success);
}
.af-node.pending .af-dot {
  background: var(--cpq-text-muted);
}
.af-title {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.af-title b {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.af-title small {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.af-latest {
  flex: 1;
  min-width: 0;
  margin-left: auto;
  text-align: right;
  font-size: 11px;
  color: var(--cpq-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.af-body {
  padding: 2px 14px 14px 46px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.af-events {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.af-event {
  display: flex;
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px dashed var(--cpq-overlay-w5);
}
.af-event:last-child {
  border-bottom: 0;
}
.af-event-dot {
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--cpq-accent-primary);
  flex: 0 0 auto;
}
.af-node.done .af-event-dot {
  background: var(--cpq-color-success);
}
.af-event-text {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  line-height: 1.6;
}
.af-event-text b {
  color: var(--cpq-text-primary);
  font-weight: 600;
}
.af-comments {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.af-comment-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.af-comment-empty {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.af-comment {
  position: relative;
  padding: 8px 9px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 8px;
  background: var(--cpq-overlay-w3);
}
.af-comment-author {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.af-comment-time {
  margin-left: 6px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.af-comment p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.af-comment-files {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 7px;
}
.af-comment-files a {
  color: #2563eb;
  font-size: 12px;
  text-decoration: none;
}
.af-comment-files a:hover {
  text-decoration: underline;
}
.af-composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.af-file-input {
  display: none;
}
.af-composer-side {
  display: flex;
  align-items: center;
  gap: 6px;
}
.af-file-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.af-file-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 7px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 6px;
  background: var(--cpq-overlay-w3);
  color: var(--cpq-text-primary);
  font-size: 12px;
}
.af-file-remove {
  border: 0;
  background: transparent;
  color: var(--cpq-text-muted);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}
.af-composer :deep(.ant-input) {
  background: var(--cpq-overlay-w3);
  border-color: var(--cpq-glass-border);
  color: var(--cpq-text-primary);
}
</style>
