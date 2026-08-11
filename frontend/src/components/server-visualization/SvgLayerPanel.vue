<script setup lang="ts">
/**
 * SvgLayerPanel —— 图层面板（编辑端右栏）。
 * 纯数据驱动：把解析后的图层树（SvgLayerNode）渲染成可操作列表，
 * 所有变更通过事件上抛，由父组件更新元数据并桥接画布。
 */
import { ref, computed } from 'vue'
import {
  EyeOutlined, EyeInvisibleOutlined, LockOutlined, UnlockOutlined,
  EditOutlined, CaretRightOutlined, CaretDownOutlined,
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
  applyTemplate: [ids: string[], prefix: string]
}>()

const checked = ref<Set<string>>(new Set())
const editingId = ref<string | null>(null)
const editName = ref('')
const collapsed = ref<Set<string>>(new Set())
const tplOpen = ref(false)

function toggleCheck(id: string) {
  const s = new Set(checked.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  checked.value = s
}

function startRename(n: SvgLayerNode) {
  editingId.value = n.id
  editName.value = n.name || n.id
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

/** 按深度扁平化图层树（折叠节点不展开子层），面板一次性渲染任意深度 */
const rows = computed(() => {
  const out: { n: SvgLayerNode; depth: number; key: string }[] = []
  let k = 0
  const walk = (nodes: SvgLayerNode[], depth: number) => {
    for (const n of nodes) {
      out.push({ n, depth, key: 'r' + k++ })
      if (n.children.length && !collapsed.value.has(n.id)) walk(n.children, depth + 1)
    }
  }
  walk(props.nodes, 0)
  return out
})

function applyTemplate(prefix: string) {
  const ids = flattenInOrder(props.nodes).filter(n => checked.value.has(n.id)).map(n => n.id)
  if (!ids.length) return
  emit('applyTemplate', ids, prefix)
  tplOpen.value = false
}
function flattenInOrder(nodes: SvgLayerNode[]): SvgLayerNode[] {
  return nodes.flatMap(n => [n, ...flattenInOrder(n.children)])
}
</script>

<template>
  <div class="slp">
    <div class="slp-toolbar">
      <a-space size="small" wrap>
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
      </a-space>
      <span class="slp-hint">勾选后可批量命名；点行同步画布</span>
    </div>

    <div class="slp-tree">
      <template v-for="{ n, depth, key } in rows" :key="key">
        <div class="slp-row" :class="{ on: activeId === n.id }" :style="{ paddingLeft: 6 + depth * 16 + 'px' }">
          <a-checkbox :checked="checked.has(n.id)" @change="toggleCheck(n.id)" />
          <span v-if="n.children.length" class="slp-caret" @click.stop="toggleCollapse(n.id)">
            <CaretDownOutlined v-if="!collapsed.has(n.id)" />
            <CaretRightOutlined v-else />
          </span>
          <span v-else class="slp-caret-placeholder" />
          <span class="slp-eye" @click.stop="emit('toggleVisible', n.id, !n.visible)">
            <EyeOutlined v-if="n.visible" />
            <EyeInvisibleOutlined v-else class="off" />
          </span>
          <span class="slp-name" :title="n.id" @click="emit('select', activeId === n.id ? null : n.id)">
            <template v-if="editingId === n.id">
              <a-input size="small" v-model:value="editName" @blur="commitRename" @pressEnter="commitRename" @click.stop />
            </template>
            <template v-else>
              {{ n.name || '（未命名）' }}
              <EditOutlined class="slp-edit" @click.stop="startRename(n)" />
            </template>
          </span>
          <span v-if="n.elCount > 1" class="slp-count">{{ n.elCount }}</span>
          <span class="slp-lock" @click.stop="emit('toggleLocked', n.id, !n.locked)">
            <LockOutlined v-if="n.locked" />
            <UnlockOutlined v-else />
          </span>
          <div class="slp-opacity">
            <a-slider :min="0" :max="100" :value="Math.round(n.opacity * 100)" size="small"
              @change="(v: number) => emit('setOpacity', n.id, (v || 0) / 100)" />
          </div>
        </div>
      </template>
      <a-empty v-if="!rows.length" description="暂无图层（SVG 解析不到分组）" :image="null" style="padding: 12px 0" />
    </div>
  </div>
</template>

<style scoped>
.slp { display: flex; flex-direction: column; gap: 8px; height: 100%; min-height: 0; }
.slp-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-shrink: 0; }
.slp-hint { color: var(--cpq-text-muted); font-size: 11px; }
.slp-tree { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.slp-row { display: flex; align-items: center; gap: 6px; padding: 3px 6px; border-radius: 8px; cursor: pointer; min-height: 30px; }
.slp-row:hover { background: var(--cpq-overlay-a6); }
.slp-row.on { background: var(--cpq-overlay-a8); outline: 1px solid var(--cpq-accent-primary); }
.slp-caret { color: var(--cpq-text-secondary); font-size: 10px; width: 12px; display: inline-flex; }
.slp-caret-placeholder { width: 12px; flex-shrink: 0; }
.slp-eye { color: var(--cpq-text-secondary); font-size: 13px; flex-shrink: 0; }
.slp-eye .off { color: var(--cpq-text-muted); }
.slp-name { flex: 1; min-width: 0; font-size: 12px; color: var(--cpq-text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.slp-edit { color: var(--cpq-text-muted); font-size: 11px; margin-left: 4px; }
.slp-count { color: var(--cpq-text-muted); font-size: 10px; flex-shrink: 0; }
.slp-lock { color: var(--cpq-text-muted); font-size: 12px; flex-shrink: 0; }
.slp-opacity { width: 72px; flex-shrink: 0; }
.slp-opacity :deep(.ant-slider) { margin: 0 4px; }
</style>
