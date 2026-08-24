<script setup lang="ts">
/**
 * SvgLayerPanel —— 图层面板（编辑端右栏）。
 * 对标 PS / AI / Figma 的图层面板交互：
 *  - 搜索 + 类型筛选（分组/形状）
 *  - 行内双击重命名、悬停出操作
 *  - 眼睛/锁常驻，hover 出更多操作
 *  - 拖拽排序（同层）与拖入分组归组
 *  - 右键菜单：重命名/排序/复制/删除/显隐/锁定
 *  - 批量选择（勾选后批量命名/显隐/锁定/删除）
 * 所有变更通过事件上抛，由父组件更新元数据并桥接画布。
 */
import { ref, computed, watch } from 'vue'
import {
  EyeOutlined, EyeInvisibleOutlined, LockOutlined, UnlockOutlined,
  EditOutlined, CaretRightOutlined, CaretDownOutlined, SearchOutlined,
  CopyOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined,
  VerticalAlignTopOutlined, VerticalAlignBottomOutlined, ClearOutlined,
} from '@ant-design/icons-vue'
import type { SvgLayerNode } from '@/utils/svgLayers'
import { LAYER_NAME_TEMPLATES } from '@/utils/svgLayers'

defineOptions({ name: 'SvgLayerPanel' })

const props = defineProps<{
  nodes: SvgLayerNode[]
  activeId: string | null
}>()

const emit = defineEmits<{
  select: [id: string | null]
  rename: [id: string, name: string]
  toggleVisible: [id: string, visible: boolean]
  toggleLocked: [id: string, locked: boolean]
  setOpacity: [id: string, opacity: number]
  reorder: [id: string, dir: 'up' | 'down' | 'top' | 'bottom']
  moveBefore: [id: string, targetId: string]
  reparent: [id: string, targetId: string]
  duplicate: [id: string]
  remove: [id: string]
  applyTemplate: [ids: string[], prefix: string]
}>()

const checked = ref<Set<string>>(new Set())
const editingId = ref<string | null>(null)
const editName = ref('')
const collapsed = ref<Set<string>>(new Set())
const collapsedInit = ref(false)
const tplOpen = ref(false)
const search = ref('')
const typeFilter = ref<'all' | 'group' | 'shape'>('all')

// ── 右键菜单 ──
const ctx = ref<{ x: number; y: number; node: SvgLayerNode } | null>(null)

// ── 拖拽 ──
const dragId = ref<string | null>(null)
const dropState = ref<{ targetId: string; kind: 'sibling' | 'group' | 'parent' } | null>(null)
const rootDrop = ref(false)

/** 无意义分组名（Figma 导出的 Group N / Rectangle N 等），默认折叠 */
const GENERIC_NAME = /^(未命名分组|未命名形状|Group|Rectangle|Vector|Ellipse|Line)s*[d_]*(s*\d+)?$/

function isGeneric(n: SvgLayerNode): boolean {
  return !n.name || GENERIC_NAME.test(n.name.trim())
}

// 首次有数据时：折叠无意义分组，让顶层清爽
watch(() => props.nodes, (nodes) => {
  if (collapsedInit.value || !nodes.length) return
  collapsedInit.value = true
  const s = new Set<string>()
  const walk = (list: SvgLayerNode[]) => {
    for (const n of list) {
      if (n.children.length && (isGeneric(n) || n.tag === 'g')) s.add(n.id)
      walk(n.children)
    }
  }
  walk(nodes)
  collapsed.value = s
}, { immediate: true })

function toggleCheck(id: string) {
  const s = new Set(checked.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  checked.value = s
}
function clearChecked() { checked.value = new Set() }

function startRename(n: SvgLayerNode) {
  editingId.value = n.id
  editName.value = n.name || n.id
  ctx.value = null
}
function commitRename() {
  if (editingId.value && editName.value.trim()) emit('rename', editingId.value, editName.value.trim())
  editingId.value = null
}

function collapseAll() { collapsed.value = new Set(allIds(props.nodes)) }
function expandAll() { collapsed.value = new Set() }
function allIds(nodes: SvgLayerNode[]): string[] {
  return nodes.flatMap(n => [n.id, ...allIds(n.children)])
}
function toggleCollapse(id: string) {
  const s = new Set(collapsed.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  collapsed.value = s
}

function findNode(nodes: SvgLayerNode[], id: string): SvgLayerNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    const f = findNode(n.children, id)
    if (f) return f
  }
  return null
}
function parentKey(n: SvgLayerNode): string {
  const find = (nodes: SvgLayerNode[]): string | null => {
    for (const p of nodes) {
      if (p.children.some(ch => ch.id === n.id)) return p.id
      const f = find(p.children)
      if (f) return f
    }
    return null
  }
  return find(props.nodes) || '__root__'
}
function isAncestor(anc: SvgLayerNode, node: SvgLayerNode): boolean {
  if (anc.id === node.id) return true
  return node.children.some(ch => isAncestor(anc, ch))
}

/** 按深度扁平化 + 搜索/类型过滤（搜索时忽略折叠） */
const rows = computed(() => {
  const kw = search.value.trim().toLowerCase()
  const filtering = !!kw || typeFilter.value !== 'all'
  const out: { n: SvgLayerNode; depth: number; key: string }[] = []
  let k = 0
  const walk = (nodes: SvgLayerNode[], depth: number) => {
    for (const n of nodes) {
      const name = (n.name || n.id).toLowerCase()
      if ((!kw || name.includes(kw)) && (typeFilter.value === 'all'
        || (typeFilter.value === 'group' && n.children.length)
        || (typeFilter.value === 'shape' && !n.children.length))) {
        out.push({ n, depth, key: 'r' + k++ })
      }
      if (n.children.length && (filtering || !collapsed.value.has(n.id))) walk(n.children, depth + 1)
    }
  }
  walk(props.nodes, 0)
  return out
})

const isFiltering = computed(() => !!search.value.trim() || typeFilter.value !== 'all')

function rowVisible(n: SvgLayerNode): boolean {
  return n.visible !== false
}

function applyTemplate(prefix: string) {
  const ids = flattenInOrder(props.nodes).filter(n => checked.value.has(n.id)).map(n => n.id)
  if (!ids.length) return
  emit('applyTemplate', ids, prefix)
  tplOpen.value = false
}
function flattenInOrder(nodes: SvgLayerNode[]): SvgLayerNode[] {
  return nodes.flatMap(n => [n, ...flattenInOrder(n.children)])
}

// ── 右键菜单 ──
function openCtx(e: MouseEvent, n: SvgLayerNode) {
  ctx.value = { x: e.clientX, y: e.clientY, node: n }
}
function closeCtx() { ctx.value = null }
function ctxAct(fn: () => void) {
  fn()
  closeCtx()
}

// ── 拖拽排序/归组 ──
function onDragStart(e: DragEvent, n: SvgLayerNode) {
  dragId.value = n.id
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}
function depthOf(n: SvgLayerNode): number {
  let d = 0
  const walk = (nodes: SvgLayerNode[], cur: number) => {
    for (const x of nodes) {
      if (x.id === n.id) { d = cur; return }
      walk(x.children, cur + 1)
    }
  }
  walk(props.nodes, 0)
  return d
}

function onDragOver(e: DragEvent, n: SvgLayerNode) {
  if (!dragId.value || dragId.value === n.id) return
  const src = findNode(props.nodes, dragId.value)
  if (!src || isAncestor(src, n)) return
  // 拖入分组（g 且有子层）→ 归组；同父级 → 排序；
  // 跨父级且目标更浅（更上层）→ 移出当前分组到目标层级
  let kind: 'group' | 'sibling' | 'parent' | null = null
  if (n.children.length && n.tag === 'g') kind = 'group'
  else if (parentKey(src) === parentKey(n)) kind = 'sibling'
  else if (depthOf(n) < depthOf(src)) kind = 'parent'
  if (!kind) return
  e.preventDefault()
  e.stopPropagation()
  if (dropState.value?.targetId !== n.id || dropState.value.kind !== kind) {
    dropState.value = { targetId: n.id, kind }
  }
}
function onDragLeave() { dropState.value = null }
function onDrop(e: DragEvent, n: SvgLayerNode) {
  e.preventDefault()
  e.stopPropagation()
  const srcId = dragId.value
  dragId.value = null
  dropState.value = null
  if (!srcId || srcId === n.id) return
  const src = findNode(props.nodes, srcId)
  if (!src || isAncestor(src, n)) return
  if (n.children.length && n.tag === 'g') {
    emit('reparent', srcId, n.id)
  } else if (parentKey(src) === parentKey(n)) {
    emit('moveBefore', srcId, n.id)
  } else if (depthOf(n) < depthOf(src)) {
    emit('reparent', srcId, n.id)
  }
}

// 拖到树内空白：移到 SVG 根层（顶层）
function onTreeDragOver(e: DragEvent) {
  if (!dragId.value) return
  e.preventDefault()
  dropState.value = null
  rootDrop.value = true
}
function onTreeDragLeave(e: DragEvent) {
  const cur = e.currentTarget as HTMLElement | null
  const rel = e.relatedTarget as Node | null
  if (!cur || !rel || !cur.contains(rel)) rootDrop.value = false
}
function onTreeDrop() {
  const srcId = dragId.value
  dragId.value = null
  rootDrop.value = false
  dropState.value = null
  if (srcId) emit('reparent', srcId, '__root__')
}
function onDragEnd() { dragId.value = null; dropState.value = null }

// ── 批量操作 ──
function batchVisible(show: boolean) {
  checked.value.forEach(id => emit('toggleVisible', id, show))
}
function batchLock(lock: boolean) {
  checked.value.forEach(id => emit('toggleLocked', id, lock))
}
function batchRemove() {
  checked.value.forEach(id => emit('remove', id))
  clearChecked()
}
</script>

<template>
  <div class="slp" @click="closeCtx">
    <div class="slp-toolbar">
      <a-input size="small" v-model:value="search" placeholder="搜索图层" allow-clear>
        <template #prefix><SearchOutlined style="color: var(--cpq-text-muted)" /></template>
      </a-input>
      <a-select v-model:value="typeFilter" size="small" style="width: 100%">
        <a-select-option value="all">全部图层</a-select-option>
        <a-select-option value="group">仅分组</a-select-option>
        <a-select-option value="shape">仅形状</a-select-option>
      </a-select>
      <div class="slp-toolbar-row">
        <a size="small" @click="expandAll">展开</a>
        <a size="small" @click="collapseAll">折叠</a>
        <a-dropdown v-model:open="tplOpen" :trigger="['click']">
          <a-button size="small">命名模板<CaretDownOutlined /></a-button>
          <template #overlay>
            <a-menu @click="(e: any) => applyTemplate(String(e.key))">
              <a-menu-item v-for="t in LAYER_NAME_TEMPLATES" :key="t.prefix">{{ t.label }}（{{ t.prefix || '自定义' }}_N）</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
      <div v-if="checked.size" class="slp-batch">
        <span class="slp-batch-num">已选 {{ checked.size }} 项</span>
        <a size="small" @click="batchVisible(true)">显示</a>
        <a size="small" @click="batchVisible(false)">隐藏</a>
        <a size="small" @click="batchLock(true)">锁定</a>
        <a size="small" @click="batchLock(false)">解锁</a>
        <a size="small" class="slp-danger" @click="batchRemove">删除</a>
        <a size="small" @click="clearChecked"><ClearOutlined /> 清空</a>
      </div>
    </div>

    <div class="slp-tree" :class="{ 'drop-root': rootDrop }" @click.self="closeCtx"
      @dragover.prevent="onTreeDragOver" @drop.prevent="onTreeDrop" @dragleave="onTreeDragLeave">
      <template v-for="{ n, depth, key } in rows" :key="key">
        <div class="slp-row"
          :class="{
            on: activeId === n.id,
            drag: dragId === n.id,
            'drop-sibling': dropState?.targetId === n.id && dropState.kind === 'sibling',
            'drop-group': dropState?.targetId === n.id && dropState.kind === 'group',
            'drop-parent': dropState?.targetId === n.id && dropState.kind === 'parent',
          }"
          :style="{ paddingLeft: 6 + depth * 16 + 'px' }"
          :draggable="editingId !== n.id"
          @dragstart="onDragStart($event, n)"
          @dragover="onDragOver($event, n)"
          @dragleave="onDragLeave"
          @drop="onDrop($event, n)"
          @dragend="onDragEnd"
          @click="emit('select', activeId === n.id ? null : n.id)"
          @dblclick="startRename(n)"
          @contextmenu.prevent="openCtx($event, n)">
          <a-checkbox :checked="checked.has(n.id)" @click.stop @change="toggleCheck(n.id)" />
          <span v-if="n.children.length" class="slp-caret" @click.stop="toggleCollapse(n.id)">
            <CaretDownOutlined v-if="!collapsed.has(n.id) && !isFiltering" />
            <CaretRightOutlined v-else />
          </span>
          <span v-else class="slp-caret-placeholder" />
          <span class="slp-eye" :class="{ off: !rowVisible(n) }" @click.stop="emit('toggleVisible', n.id, !n.visible)">
            <EyeOutlined v-if="n.visible" />
            <EyeInvisibleOutlined v-else />
          </span>
          <span class="slp-name" :title="n.name || n.id">
            <template v-if="editingId === n.id">
              <a-input size="small" v-model:value="editName" @blur="commitRename" @pressEnter="commitRename" @click.stop @dblclick.stop />
            </template>
            <template v-else>
              <span class="slp-name-txt">{{ n.name || '（未命名）' }}</span>
              <EditOutlined class="slp-edit" @click.stop="startRename(n)" />
            </template>
          </span>
          <span v-if="n.elCount > 1" class="slp-count">{{ n.elCount }}</span>
          <span class="slp-lock" :class="{ on: n.locked }" @click.stop="emit('toggleLocked', n.id, !n.locked)">
            <LockOutlined v-if="n.locked" />
            <UnlockOutlined v-else />
          </span>
        </div>
      </template>
      <a-empty v-if="!rows.length" :description="search || typeFilter !== 'all' ? '没有匹配的图层' : '暂无图层（SVG 解析不到分组）'" :image="null" style="padding: 12px 0" />
    </div>

    <!-- 右键菜单 -->
    <div v-if="ctx" class="slp-ctx" :style="{ left: ctx.x + 'px', top: ctx.y + 'px' }" @click.stop @contextmenu.prevent>
      <div class="slp-ctx-title" :title="ctx.node.name || ctx.node.id">{{ ctx.node.name || '（未命名）' }}</div>
      <a class="slp-ctx-item" @click="ctxAct(() => startRename(ctx!.node))"><EditOutlined /> 重命名</a>
      <a class="slp-ctx-item" @click="ctxAct(() => emit('toggleVisible', ctx!.node.id, !ctx!.node.visible))">
        <EyeOutlined v-if="ctx.node.visible" /><EyeInvisibleOutlined v-else /> {{ ctx.node.visible ? '隐藏' : '显示' }}
      </a>
      <a class="slp-ctx-item" @click="ctxAct(() => emit('toggleLocked', ctx!.node.id, !ctx!.node.locked))">
        <LockOutlined v-if="ctx.node.locked" /><UnlockOutlined v-else /> {{ ctx.node.locked ? '解锁' : '锁定' }}
      </a>
      <div class="slp-ctx-sep" />
      <a class="slp-ctx-item" @click="ctxAct(() => emit('reorder', ctx!.node.id, 'up'))"><ArrowUpOutlined /> 上移</a>
      <a class="slp-ctx-item" @click="ctxAct(() => emit('reorder', ctx!.node.id, 'down'))"><ArrowDownOutlined /> 下移</a>
      <a class="slp-ctx-item" @click="ctxAct(() => emit('reorder', ctx!.node.id, 'top'))"><VerticalAlignTopOutlined /> 置顶</a>
      <a class="slp-ctx-item" @click="ctxAct(() => emit('reorder', ctx!.node.id, 'bottom'))"><VerticalAlignBottomOutlined /> 置底</a>
      <div class="slp-ctx-sep" />
      <a class="slp-ctx-item" @click="ctxAct(() => emit('duplicate', ctx!.node.id))"><CopyOutlined /> 复制</a>
      <a class="slp-ctx-item slp-danger" @click="ctxAct(() => emit('remove', ctx!.node.id))"><DeleteOutlined /> 删除</a>
    </div>
  </div>
</template>

<style scoped>
.slp { position: relative; display: flex; flex-direction: column; gap: 8px; height: 100%; min-height: 0; }
.slp-toolbar { display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }
.slp-toolbar-row { display: flex; align-items: center; gap: 10px; }
.slp-batch { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 8px;
  background: var(--cpq-overlay-a6); border: 1px solid var(--cpq-glass-border); font-size: 12px; flex-wrap: wrap; }
.slp-batch-num { color: var(--cpq-accent-primary); margin-right: 2px; }
.slp-danger { color: #ff4d4f; }
.slp-tree { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; padding: 2px 0; }
.slp-row { position: relative; display: flex; align-items: center; gap: 6px; padding: 3px 6px;
  border-radius: 8px; cursor: pointer; min-height: 30px; border: 1px solid transparent; }
.slp-row:hover { background: var(--cpq-overlay-a6); }
.slp-row.on { background: var(--cpq-overlay-a8); outline: 1px solid var(--cpq-accent-primary); }
.slp-row.drag { opacity: 0.4; }
.slp-row.drop-sibling::before { content: ''; position: absolute; left: 4px; right: 4px; top: -2px; height: 2px;
  border-radius: 2px; background: var(--cpq-accent-primary); }
.slp-row.drop-group { outline: 2px dashed var(--cpq-accent-primary); background: var(--cpq-overlay-a8); }
.slp-row.drop-parent { outline: 2px dashed var(--cpq-accent-primary); background: var(--cpq-overlay-a8); }
.slp-tree.drop-root { outline: 2px dashed var(--cpq-accent-primary); border-radius: 8px; background: var(--cpq-overlay-a6); }
.slp-caret { color: var(--cpq-text-secondary); font-size: 10px; width: 12px; display: inline-flex; flex-shrink: 0; }
.slp-caret-placeholder { width: 12px; flex-shrink: 0; }
.slp-eye { color: var(--cpq-text-secondary); font-size: 13px; flex-shrink: 0; cursor: pointer; }
.slp-eye.off { color: var(--cpq-text-muted); opacity: 0.55; }
.slp-name { flex: 1; min-width: 0; font-size: 12px; color: var(--cpq-text-primary);
  display: flex; align-items: center; gap: 4px; }
.slp-name-txt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.slp-edit { color: var(--cpq-text-muted); font-size: 11px; opacity: 0; transition: opacity 0.12s; flex-shrink: 0; }
.slp-row:hover .slp-edit, .slp-row.on .slp-edit { opacity: 1; }
.slp-count { color: var(--cpq-text-muted); font-size: 10px; flex-shrink: 0; }
.slp-lock { color: var(--cpq-text-muted); font-size: 12px; flex-shrink: 0; cursor: pointer; }
.slp-lock.on { color: var(--cpq-accent-primary); }
.slp-ctx { position: fixed; z-index: 2000; min-width: 150px; padding: 4px; border-radius: 10px;
  background: var(--cpq-overlay-solid, #1e2430); border: 1px solid var(--cpq-glass-border);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); display: flex; flex-direction: column; }
.slp-ctx-title { font-size: 12px; font-weight: 600; color: var(--cpq-text-primary); padding: 4px 8px 6px;
  max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.slp-ctx-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--cpq-text-primary);
  padding: 5px 8px; border-radius: 6px; cursor: pointer; }
.slp-ctx-item:hover { background: var(--cpq-accent-primary); color: #fff; }
.slp-ctx-sep { height: 1px; margin: 3px 6px; background: var(--cpq-glass-border); }
</style>
