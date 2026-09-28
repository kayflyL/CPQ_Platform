<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { FeedAttachment, FeedMessage } from '@/api/feed'
import type { ApprovalItem, FlowCard, FlowInfo, FlowNode, PortalOpp } from '@/api/portal'
import { useFeedSocket } from '@/composables/useFeedSocket'
import { feedApi } from '@/api/feed'
import { downloadOfficeFile } from '@/utils/fileDownload'
import { fmtTime } from '@/utils/quoteCommon'

async function downloadAtt(att: FeedAttachment) {
  try {
    await downloadOfficeFile(feedApi.attachments.downloadUrl(att.attachment_id), att.original_filename)
  } catch {
    message.error('下载失败')
  }
}

const props = defineProps<{
  opportunityId: string
  nodes: FlowNode[]
  currentNode: string
  activeNode?: string
  flowCards?: FlowCard[]
  approvals?: ApprovalItem[]
  flow?: FlowInfo | null
  opportunity?: PortalOpp['opportunity'] | null
}>()

const NODE_DEFS = [
  { key: 'requirement', title: '线索登记', label: '业务' },
  { key: 'boming', title: '方案配置', label: '技术支持' },
  { key: 'costing', title: '成本核算', label: '成本核算' },
  { key: 'quoting', title: '报价单', label: '市场报价' },
]

const NODE_LABELS: Record<string, string> = {
  requirement: '需求单',
  boming: '方案配置',
  costing: '成本核算',
  quoting: '报价单',
}

const draft = ref('')
const sending = ref(false)
const selectedFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const opportunityIdRef = computed(() => props.opportunityId)
const feed = useFeedSocket(opportunityIdRef)
const { messages } = feed
const filter = ref<'all' | 'current' | 'comments'>('all')
const now = ref(Date.now())
let clockTimer: number | undefined
const activeNodeKey = computed(() => props.activeNode || props.currentNode || 'requirement')

function msgNodeKey(m: FeedMessage): string {
  return m.node_key || 'requirement'
}

function toTimestamp(value?: string): number {
  if (!value) return 0
  const t = new Date(value).getTime()
  return Number.isNaN(t) ? 0 : t
}

function displayName(name?: string): string {
  return name?.trim() || '系统'
}

function avatarChar(name?: string): string {
  const text = displayName(name)
  return text === '系统' ? '系' : text.slice(0, 1)
}

function durationText(value?: string): string {
  const t = toTimestamp(value)
  if (!t) return '—'
  const diff = Math.max(0, now.value - t)
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时`
  return `${Math.floor(hours / 24)} 天`
}

function nodeLabel(nodeKey: string): string {
  return NODE_LABELS[nodeKey] || NODE_DEFS.find((n) => n.key === nodeKey)?.title || nodeKey
}

const currentApproval = computed(() => props.approvals?.find((a) => a.key === props.currentNode) || null)
const currentNodeDef = computed(() => NODE_DEFS.find((n) => n.key === props.currentNode) || NODE_DEFS[0])
const opportunityHandler = computed(() => {
  const opp = props.opportunity
  if (!opp) return ''
  if (props.currentNode === 'requirement') return opp.sales_person || ''
  if (props.currentNode === 'boming') return opp.fae || ''
  if (props.currentNode === 'quoting') return opp.quotation_person || ''
  return ''
})
const currentHandler = computed(() =>
  props.flow?.assignees?.[props.currentNode]
  || latestEvent(props.currentNode)?.actor
  || opportunityHandler.value
  || currentApproval.value?.assignee
  || '待指派',
)
const currentStateLabel = computed(() => currentApproval.value?.status_label || stateText(props.currentNode))
const currentVersion = computed(() => latestEvent(props.currentNode)?.version_tag || '—')
const currentLatestText = computed(() => durationText(latestEvent(props.currentNode)?.created_at))
const stayText = computed(() => {
  const events = eventsFor(props.currentNode)
  const start = events.find((e) => ['assign', 'draft'].includes(e.action)) || events[0]
  return durationText(start?.created_at)
})

type FeedRow =
  | { id: string; kind: 'event'; nodeKey: string; actor: string; time: string; text: string; createdAt: number }
  | { id: string; kind: 'comment'; nodeKey: string; actor: string; time: string; text: string; createdAt: number; attachments: FeedMessage['attachments'] }

const eventRows = computed<FeedRow[]>(() =>
  props.nodes.map((n, index) => ({
    id: `event-${n.id ?? index}`,
    kind: 'event',
    nodeKey: n.node_key,
    actor: n.actor || '系统',
    time: n.created_at,
    text: `${actionText(n)}${n.comment ? `：${n.comment}` : ''}`,
    createdAt: toTimestamp(n.created_at),
  })),
)

const commentRows = computed<FeedRow[]>(() =>
  messages.value
    .filter((m) => m.kind === 'comment' && (m.body || m.attachments?.length))
    .map((m) => ({
      id: `comment-${m.message_id}`,
      kind: 'comment',
      nodeKey: msgNodeKey(m),
      actor: m.author_name || '匿名',
      time: m.created_at,
      text: m.body || '',
      createdAt: toTimestamp(m.created_at),
      attachments: m.attachments || [],
    })),
)

const feedRows = computed<FeedRow[]>(() => {
  const rows = [...eventRows.value, ...commentRows.value]
  const filtered = filter.value === 'current'
    ? rows.filter((r) => r.nodeKey === activeNodeKey.value)
    : filter.value === 'comments'
      ? rows.filter((r) => r.kind === 'comment')
      : rows
  return filtered.sort((a, b) => b.createdAt - a.createdAt)
})

const feedTabs = [
  { key: 'all', label: '全部动态' },
  { key: 'current', label: '选中节点' },
  { key: 'comments', label: '评论' },
] as const

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

function stateText(state: string): string {
  return state === 'done' ? '已完成' : state === 'current' ? '处理中' : '待处理'
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

function setFilter(key: typeof filter.value) {
  filter.value = key
}

function cardIdForNode(nodeKey: string): number | null {
  const card = (props.flowCards || []).find(
    (c) => c.current_node === nodeKey && ['submitted', 'processing', 'returned'].includes(c.flow_status),
  )
  return card?.id ?? null
}

onMounted(() => {
  activate()
  clockTimer = window.setInterval(() => {
    now.value = Date.now()
  }, 60000)
})
watch(() => props.opportunityId, () => {
  filter.value = 'all'
  activate()
})
onBeforeUnmount(() => {
  feed.disconnect()
  if (clockTimer) window.clearInterval(clockTimer)
})
</script>

<template>
  <div class="approval-flow">
    <input ref="fileInput" type="file" multiple class="af-file-input" @change="onFilesPicked" />

    <section class="af-current">
      <div class="af-current-head">
        <span class="af-avatar">{{ avatarChar(currentHandler) }}</span>
        <div class="af-current-copy">
          <span class="af-eyebrow">当前处理人</span>
          <b>{{ currentHandler }} · {{ currentNodeDef.title }}</b>
          <small>{{ currentNodeDef.label }} · {{ currentStateLabel }}</small>
        </div>
        <span class="af-status" :class="{ done: currentApproval?.state === 'done' }">{{ currentStateLabel }}</span>
      </div>

      <div class="af-metrics">
        <div><span>最近更新</span><b>{{ currentLatestText }}</b></div>
        <div><span>已停留</span><b>{{ stayText }}</b></div>
        <div><span>版本</span><b>{{ currentVersion }}</b></div>
      </div>

    </section>

    <div class="af-tabs">
      <button
        v-for="tab in feedTabs"
        :key="tab.key"
        type="button"
        :class="{ active: filter === tab.key }"
        @click="setFilter(tab.key)"
      >{{ tab.label }}</button>
    </div>

    <section class="af-feed">
      <div v-if="!feedRows.length" class="af-empty">暂无动态</div>
      <article v-for="row in feedRows" :key="row.id" class="af-feed-item">
        <span class="af-avatar sm" :class="row.kind">{{ avatarChar(row.actor) }}</span>
        <div class="af-feed-copy">
          <b>{{ row.actor }} · {{ row.kind === 'comment' ? '评论' : row.text }}</b>
          <small><em class="af-node-chip">{{ nodeLabel(row.nodeKey) }}</em> · {{ fmtTime(row.time) }}</small>
          <p v-if="row.kind === 'comment' && row.text">{{ row.text }}</p>
          <div v-if="row.kind === 'comment' && row.attachments?.length" class="af-attach-list">
            <a
              v-for="att in row.attachments"
              :key="att.attachment_id"
              @click.prevent="downloadAtt(att)"
            >📎 {{ att.original_filename }}</a>
          </div>
        </div>
      </article>
    </section>

    <section class="af-composer">
      <div class="af-composer-head">
        <span>回复：{{ nodeLabel(activeNodeKey) }}</span>
      </div>
      <a-textarea
        v-model:value="draft"
        placeholder="输入回复内容，可使用 @ 提醒处理人..."
        :auto-size="{ minRows: 1, maxRows: 3 }"
        :disabled="sending"
        @press-enter="(e: KeyboardEvent) => { if (!e.shiftKey) { e.preventDefault(); postComment(activeNodeKey) } }"
      />
      <div class="af-composer-foot">
        <div v-if="selectedFiles.length" class="af-file-chips">
          <span v-for="(f, i) in selectedFiles" :key="`${f.name}-${i}`" class="af-file-chip">
            📎 {{ f.name }}
            <button type="button" class="af-file-remove" @click="removeSelectedFile(i)">×</button>
          </span>
        </div>
        <div class="af-composer-actions">
          <a-button size="small" :disabled="sending" @click="chooseFiles">附件</a-button>
          <a-button type="primary" size="small" :loading="sending" :disabled="!draft.trim() && !selectedFiles.length" @click="postComment(activeNodeKey)">
            回复
          </a-button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.approval-flow {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 10px 10px 12px 12px;
}
.af-feed::-webkit-scrollbar {
  width: 6px;
}
.af-feed::-webkit-scrollbar-thumb {
  background: var(--cpq-overlay-a20);
  border-radius: 3px;
}
.af-feed::-webkit-scrollbar-track {
  background: transparent;
}
.af-file-input {
  display: none;
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
.af-current {
  flex: none;
  padding: 11px;
  margin-bottom: 10px;
  border: 1px solid var(--cpq-accent-primary);
  border-radius: 11px;
  background: linear-gradient(135deg, var(--cpq-overlay-a10), transparent), var(--cpq-bg-elevated);
  box-shadow: 0 10px 20px -22px rgba(0, 0, 0, 0.65);
}
.af-current-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.af-avatar {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--cpq-accent-primary);
  color: #fff;
  font-weight: 700;
  font-size: 12px;
}
.af-avatar.sm {
  width: 22px;
  height: 22px;
  margin-top: 1px;
  font-size: 10px;
}
.af-avatar.comment {
  background: #8b5cf6;
}
.af-current-copy {
  flex: 1;
  min-width: 0;
}
.af-eyebrow {
  display: block;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.af-current-copy b {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.af-current-copy small {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  color: var(--cpq-text-muted);
}
.af-status {
  flex: 0 0 auto;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
  font-size: 10px;
  font-weight: 700;
}
.af-status.done {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}
.af-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 7px;
  margin-top: 9px;
}
.af-metrics div {
  min-width: 0;
}
.af-metrics span {
  display: block;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.af-metrics b {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--cpq-text-primary);
  white-space: nowrap;
}
.af-tabs {
  display: flex;
  flex: none;
  gap: 6px;
  margin-bottom: 6px;
}
.af-tabs button {
  border: 0;
  background: transparent;
  color: var(--cpq-text-muted);
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 11px;
  cursor: pointer;
}
.af-tabs button.active {
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
  font-weight: 700;
}
.af-feed {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  border-top: 1px solid var(--cpq-overlay-w5);
}
.af-empty {
  padding: 14px 0;
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.af-feed-item {
  display: flex;
  gap: 9px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--cpq-overlay-w5);
}
.af-feed-item:last-child {
  border-bottom: 0;
}
.af-feed-copy {
  flex: 1;
  min-width: 0;
}
.af-feed-copy b {
  display: block;
  font-size: 11.5px;
  color: var(--cpq-text-primary);
}
.af-feed-copy small {
  display: block;
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--cpq-text-muted);
}
.af-node-chip {
  display: inline-block;
  margin-right: 4px;
  padding: 1px 6px;
  border-radius: 5px;
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
  font-style: normal;
}
.af-feed-copy p {
  margin: 5px 0 0;
  font-size: 12px;
  color: var(--cpq-text-secondary);
  line-height: 1.5;
}
.af-attach-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 7px;
}
.af-attach-list a {
  color: #2563eb;
  font-size: 12px;
  text-decoration: none;
}
.af-attach-list a:hover {
  text-decoration: underline;
}
.af-composer {
  flex: none;
  margin-top: 10px;
  display: block;
}
.af-composer :deep(.ant-input) {
  background: var(--cpq-overlay-w3);
  border-color: var(--cpq-glass-border);
  color: var(--cpq-text-primary);
  font-size: 12px;
  line-height: 1.5;
}
.af-composer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 10.5px;
  color: var(--cpq-text-muted);
}
.af-composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}
.af-composer-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}
</style>
