<template>
  <div class="space-editor">
    <div class="se-toolbar">
      <div>
        <h3>空间布局</h3>
        <p>在平面图上直接拖拽工位、会议区；选中后可微调坐标、朝向和角色绑定。</p>
      </div>
      <div class="se-toolbar-actions">
        <a-button @click="deselect">取消选择</a-button>
      </div>
    </div>

    <div class="se-layout">
      <aside class="se-library">
        <div class="se-card">
          <div class="se-card-title">家具库</div>
          <div class="se-library-tip">点击添加到画布中央，再在平面图中拖拽、旋转。</div>
          <div v-for="group in furnitureGroups" :key="group.category" class="se-furniture-group">
            <div class="se-furniture-group-title">{{ group.label }}</div>
            <button
              v-for="item in group.items"
              :key="item.type"
              type="button"
              class="se-furniture-item"
              @click="addFurniture(item.type)"
            >
              <span class="se-furniture-emoji">{{ furnitureEmoji(item.type) }}</span>
              <span class="se-furniture-label">{{ item.label }}</span>
            </button>
          </div>
        </div>
      </aside>

      <main class="se-plan-panel">
        <svg
          ref="svgRef"
          class="se-plan"
          :viewBox="viewBox"
          preserveAspectRatio="xMidYMid meet"
          @pointerdown="deselect"
        >
          <rect
            class="se-workspace"
            :x="planX(-draft.workspace.width / 2)"
            :y="planY(draft.workspace.depth / 2)"
            :width="draft.workspace.width"
            :height="draft.workspace.depth"
            rx="2"
          />

          <g v-for="line in gridLines" :key="'v-' + line">
            <line
              class="se-grid-line"
              :x1="planX(-draft.workspace.width / 2 + line)"
              :y1="planY(draft.workspace.depth / 2)"
              :x2="planX(-draft.workspace.width / 2 + line)"
              :y2="planY(-draft.workspace.depth / 2)"
            />
          </g>
          <g v-for="line in gridLines" :key="'h-' + line">
            <line
              class="se-grid-line"
              :x1="planX(-draft.workspace.width / 2)"
              :y1="planY(draft.workspace.depth / 2 - line)"
              :x2="planX(draft.workspace.width / 2)"
              :y2="planY(draft.workspace.depth / 2 - line)"
            />
          </g>

          <rect
            class="se-floor"
            :x="planX(-draft.floor.width / 2)"
            :y="planY(draft.floor.depth / 2)"
            :width="draft.floor.width"
            :height="draft.floor.depth"
            rx="0.6"
          />
          <text class="se-area-label" :x="planX(0)" :y="planY(draft.floor.depth / 2 - 1.2)" text-anchor="middle">办公区</text>

          <g v-for="(zone, zoneIndex) in draft.zones" :key="zone.id">
            <g v-if="zone.type === 'meeting'" :transform="zoneTransform(zone)">
              <rect
                class="meeting-carpet"
                :width="meetingRoomSize(zone).width"
                :height="meetingRoomSize(zone).depth"
                :x="-meetingRoomSize(zone).width / 2"
                :y="-meetingRoomSize(zone).depth / 2"
                rx="0.35"
                @pointerdown.stop="startMeetingDrag($event, zoneIndex)"
              />
              <rect
                class="meeting-table"
                :width="meetingTableSize(zone).width"
                :height="meetingTableSize(zone).depth"
                :x="-meetingTableSize(zone).width / 2"
                :y="-meetingTableSize(zone).depth / 2"
                rx="0.12"
                @pointerdown.stop="startMeetingDrag($event, zoneIndex)"
              />
              <circle
                v-for="(slot, slotIndex) in zone.slots"
                :key="slot.id || zone.id + '-' + slotIndex"
                class="meeting-slot"
                :class="{ selected: isSelectedSlot(zoneIndex, slotIndex) }"
                :cx="planDeltaX(slot.position.x, zone.position.x)"
                :cy="planDeltaY(slot.position.z, zone.position.z)"
                r="0.18"
                @pointerdown.stop="startSlotDrag($event, zoneIndex, slotIndex)"
              />
            </g>

            <g
              v-if="zone.type !== 'desk' && zone.type !== 'meeting'"
              :transform="zoneTransform(zone)"
              class="zone-footprint"
              @pointerdown.stop="startZoneDrag($event, zoneIndex)"
            >
              <rect
                v-if="zone.shape === 'rect'"
                class="zone-footprint-shape"
                :class="{ selected: isSelectedZone(zoneIndex) }"
                :width="zoneShapeSize(zone).width"
                :height="zoneShapeSize(zone).depth"
                :x="-zoneShapeSize(zone).width / 2"
                :y="-zoneShapeSize(zone).depth / 2"
                rx="0.3"
              />
              <circle
                v-else
                class="zone-footprint-shape"
                :class="{ selected: isSelectedZone(zoneIndex) }"
                :r="zone.radius || 3.2"
              />
              <text class="zone-footprint-label" text-anchor="middle" y="-4.0">{{ zone.label || zone.id }}</text>
            </g>

            <g
              v-for="(slot, slotIndex) in deskSlots(zone)"
              :key="slot.id || zone.id + '-' + slotIndex"
              :transform="slotTransform(slot.position)"
              class="desk-slot"
              @pointerdown.stop="startSlotDrag($event, zoneIndex, slotIndex)"
            >
              <rect
                class="desk-body"
                :class="{ selected: isSelectedSlot(zoneIndex, slotIndex) }"
                x="-0.82"
                y="-0.48"
                width="1.64"
                height="0.96"
                rx="0.12"
              />
              <line class="desk-direction" x1="0" y1="0" :x2="Math.sin(slot.rotation_y) * 0.62" :y2="-Math.cos(slot.rotation_y) * 0.62" />
            </g>
          </g>

          <g v-for="zone in meetingZones" :key="'connection-' + zone.id">
            <rect v-if="connectionRect(zone)" class="se-door-corridor" v-bind="connectionRect(zone)" />
          </g>

          <g
            v-for="(item, furnitureIndex) in draft.furniture"
            :key="item.id || furnitureIndex"
            class="furniture-item"
            :transform="furnitureTransform(item)"
            @pointerdown.stop="startFurnitureDrag($event, furnitureIndex)"
          >
            <rect
              class="furniture-body"
              :class="{ selected: isSelectedFurniture(furnitureIndex) }"
              :width="furnitureSize(item).width"
              :height="furnitureSize(item).depth"
              :x="-furnitureSize(item).width / 2"
              :y="-furnitureSize(item).depth / 2"
              rx="0.16"
            />
            <text class="furniture-label" text-anchor="middle" y="0.12">{{ furnitureLabel(item) }}</text>
          </g>
        </svg>
        <div v-if="validationIssues.length" class="se-plan-warning">{{ validationIssues[0] }}</div>
        <div class="se-plan-hint">拖拽家具/工位/会议室 · 点击空白取消选择 · 保存后 3D 办公室会刷新</div>
      </main>

            <aside class="se-props">
        <div class="se-card">
          <div class="se-card-title">空间画布</div>
          <label class="se-field">
            <span>画布宽度</span>
            <a-input-number v-model:value="draft.workspace.width" :min="24" :max="120" />
          </label>
          <label class="se-field">
            <span>画布深度</span>
            <a-input-number v-model:value="draft.workspace.depth" :min="16" :max="120" />
          </label>
        </div>

        <div class="se-card">
          <div class="se-card-title">办公区尺寸</div>
          <label class="se-field">
            <span>宽度</span>
            <a-input-number v-model:value="draft.floor.width" :min="8" :max="80" />
          </label>
          <label class="se-field">
            <span>深度</span>
            <a-input-number v-model:value="draft.floor.depth" :min="8" :max="80" />
          </label>
        </div>

        <div class="se-card">
          <div class="se-card-title">办公室主题</div>
          <label class="se-field">
            <span>预设风格</span>
            <a-select v-model:value="draft.environment_theme.preset" style="width: 100%">
              <a-select-option value="midnight">午夜蓝</a-select-option>
              <a-select-option value="daylight">日光白</a-select-option>
              <a-select-option value="warm-loft">暖木阁楼</a-select-option>
            </a-select>
          </label>
          <label class="se-field se-switch">
            <span>落地窗</span>
            <a-switch v-model:checked="themeProps.windows" />
          </label>
          <label class="se-field se-switch">
            <span>绿植</span>
            <a-switch v-model:checked="themeProps.plants" />
          </label>
          <label class="se-field se-switch">
            <span>书架</span>
            <a-switch v-model:checked="themeProps.bookshelves" />
          </label>
          <label class="se-field se-switch">
            <span>茶水间</span>
            <a-switch v-model:checked="themeProps.coffee_bar" />
          </label>
          <label class="se-field se-switch">
            <span>休息区</span>
            <a-switch v-model:checked="themeProps.lounge" />
          </label>
          <label class="se-field se-switch">
            <span>白板 / 装饰画</span>
            <a-switch v-model:checked="themeProps.whiteboard" />
          </label>
        </div>

        <div class="se-card">
          <div class="se-card-title">空间区域</div>
          <div v-if="!draft.zones.length" class="se-zone-empty">暂无区域，点击下方新增。</div>
          <button
            v-for="(zone, zoneIndex) in draft.zones"
            :key="zone.id"
            type="button"
            class="se-zone-item"
            :class="{ selected: isSelectedZone(zoneIndex) }"
            @click="selectZone(zoneIndex)"
          >
            <span class="se-zone-name">{{ zone.label || zone.id }}</span>
            <span class="se-zone-meta">{{ zoneTypeLabel(zone.type) }} · {{ zoneWalkTargetLabel(zone.walk_target) }}</span>
          </button>
          <a-button block @click="addZone">新增区域</a-button>
        </div>

        <div v-if="selectedZone" class="se-card">
          <div class="se-card-title">区域设置</div>
          <label class="se-field">
            <span>区域 ID</span>
            <a-input v-model:value="selectedZone.id" placeholder="例如 public_zone" />
          </label>
          <label class="se-field">
            <span>显示名称</span>
            <a-input v-model:value="selectedZone.label" placeholder="例如 办公室公共区" />
          </label>
          <label class="se-field">
            <span>区域类型</span>
            <a-select v-model:value="selectedZone.type">
              <a-select-option value="desk">工位区</a-select-option>
              <a-select-option value="meeting">会议室</a-select-option>
              <a-select-option value="public">公共区</a-select-option>
              <a-select-option value="lounge">休息区</a-select-option>
              <a-select-option value="lobby">接待区</a-select-option>
            </a-select>
          </label>
          <label class="se-field">
            <span>自然语言别名</span>
            <a-select v-model:value="selectedZone.aliases" mode="tags" :token-separators="zoneAliasSeparators" placeholder="输入别名后回车" />
          </label>
          <label class="se-field">
            <span>到达落点</span>
            <a-select v-model:value="selectedZone.walk_target">
              <a-select-option value="home">回到本人工位</a-select-option>
              <a-select-option value="center">走到区域中心</a-select-option>
              <a-select-option value="meeting">走到会议座位</a-select-option>
              <a-select-option value="slot">走到区域内座位</a-select-option>
            </a-select>
          </label>
          <template v-if="selectedZone.type !== 'meeting' && selectedZone.type !== 'desk'">
            <label class="se-field">
              <span>中心 X</span>
              <a-input-number v-model:value="selectedZone.position.x" :step="0.1" />
            </label>
            <label class="se-field">
              <span>中心 Z</span>
              <a-input-number v-model:value="selectedZone.position.z" :step="0.1" />
            </label>
            <label class="se-field">
              <span>形状</span>
              <a-select v-model:value="selectedZone.shape">
                <a-select-option value="circle">圆形</a-select-option>
                <a-select-option value="rect">矩形</a-select-option>
              </a-select>
            </label>
            <label v-if="selectedZone.shape !== 'rect'" class="se-field">
              <span>半径</span>
              <a-input-number v-model:value="selectedZone.radius" :min="0.5" :step="0.1" />
            </label>
            <template v-else>
              <label class="se-field">
                <span>宽度</span>
                <a-input-number v-model:value="selectedZone.width" :min="0.5" :step="0.1" />
              </label>
              <label class="se-field">
                <span>深度</span>
                <a-input-number v-model:value="selectedZone.depth" :min="0.5" :step="0.1" />
              </label>
            </template>
          </template>
          <div class="se-prop-actions">
            <a-button danger block @click="deleteSelectedZone">删除区域</a-button>
          </div>
        </div>

        <div v-if="selectedSlot || selectedMeeting || selectedFurniture" class="se-card">
          <div class="se-card-title">{{ selectedTitle }}</div>

          <template v-if="selected?.kind === 'slot' && selectedSlot">
            <label class="se-field">
              <span>X</span>
              <a-input-number v-model:value="selectedSlot.position.x" :step="0.1" />
            </label>
            <label class="se-field">
              <span>Z</span>
              <a-input-number v-model:value="selectedSlot.position.z" :step="0.1" />
            </label>
            <label class="se-field">
              <span>朝向</span>
              <a-input-number v-model:value="selectedSlot.rotation_y" :step="0.1" />
            </label>
            <label class="se-field">
              <span>绑定角色</span>
              <a-select
                v-model:value="selectedSlot.role_key"
                :options="colleagueOptions"
                allow-clear
                placeholder="留空自动分配"
              />
            </label>
          </template>

          <template v-else-if="selectedMeeting">
            <label class="se-field">
              <span>中心 X</span>
              <a-input-number v-model:value="selectedMeeting.position.x" :step="0.1" />
            </label>
            <label class="se-field">
              <span>中心 Z</span>
              <a-input-number v-model:value="selectedMeeting.position.z" :step="0.1" />
            </label>
            <label class="se-field">
              <span>宽度</span>
              <a-input-number v-model:value="selectedMeeting.width" :min="6" :max="30" :step="0.1" />
            </label>
            <label class="se-field">
              <span>深度</span>
              <a-input-number v-model:value="selectedMeeting.depth" :min="4" :max="20" :step="0.1" />
            </label>
            <label class="se-field">
              <span>半径</span>
              <a-input-number v-model:value="selectedMeeting.radius" :min="0.5" :step="0.1" />
            </label>
            <label class="se-field">
              <span>容量</span>
              <a-input-number v-model:value="selectedMeeting.capacity" :min="1" />
            </label>
          </template>

          <template v-else-if="selected?.kind === 'furniture' && selectedFurniture">
            <div class="se-furniture-name">{{ furnitureLabel(selectedFurniture) }}</div>
            <label class="se-field">
              <span>X</span>
              <a-input-number v-model:value="selectedFurniture.position.x" :step="0.1" />
            </label>
            <label class="se-field">
              <span>Z</span>
              <a-input-number v-model:value="selectedFurniture.position.z" :step="0.1" />
            </label>
            <label class="se-field">
              <span>朝向</span>
              <a-input-number v-model:value="selectedFurniture.rotation_y" :step="0.1" />
            </label>
            <div class="se-prop-actions">
              <a-button @click="rotateSelectedFurniture">旋转 90°</a-button>
              <a-button danger @click="deleteSelectedFurniture">删除</a-button>
            </div>
          </template>
        </div>

        <div v-else class="se-empty-props">
          点击平面图中的工位、会议室或家具进行编辑
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { officeApi, type FurnitureDefinition, type OfficeConfig, type OfficeEnvironmentTheme, type OfficeFurnitureItem, type OfficeZone } from '@/api/office'

const props = defineProps<{ officeConfig?: OfficeConfig; colleagues?: any[] }>()
const emit = defineEmits<{ saved: [] }>()

interface SpaceSlot {
  id: string
  role_key?: string | null
  position: { x: number; z: number }
  rotation_y: number
}

interface SpaceZone extends OfficeZone {
  position: { x: number; z: number }
  radius?: number
  capacity?: number
  slots: SpaceSlot[]
}

interface SpaceDraft {
  floor: { width: number; depth: number }
  workspace: { width: number; depth: number }
  zones: SpaceZone[]
  furniture: OfficeFurnitureItem[]
  furniture_catalog: FurnitureDefinition[]
  character_models?: string[]
  status_zone_map?: Record<string, string>
  environment_theme: OfficeEnvironmentTheme
}

type Selection =
  | { kind: 'slot'; zoneIndex: number; slotIndex: number }
  | { kind: 'meeting'; zoneIndex: number }
  | { kind: 'zone'; zoneIndex: number }
  | { kind: 'furniture'; furnitureIndex: number }

type DragState =
  | { kind: 'slot'; zoneIndex: number; slotIndex: number; offset: { x: number; z: number } }
  | { kind: 'meeting'; zoneIndex: number; offset: { x: number; z: number } }
  | { kind: 'zone'; zoneIndex: number; offset: { x: number; z: number } }
  | { kind: 'furniture'; furnitureIndex: number; offset: { x: number; z: number } }

const svgRef = ref<SVGSVGElement | null>(null)
const saving = ref(false)
const selected = ref<Selection | null>(null)
const drag = ref<DragState | null>(null)
const pad = 3
const zoneAliasSeparators = [',', '，']
const ZONE_TYPE_LABELS: Record<string, string> = { desk: '工位区', meeting: '会议室', public: '公共区', lounge: '休息区', lobby: '接待区' }
const WALK_TARGET_LABELS: Record<string, string> = { home: '回到本人工位', center: '走到区域中心', meeting: '走到会议座位', slot: '走到区域内座位' }
const colleagueOptions = computed(() =>
  (props.colleagues || []).map((colleague) => ({
    value: colleague.role_key,
    label: `${colleague.name || colleague.role_key} (${colleague.role_key})`,
  })),
)

function defaultWalkTarget(type: string): OfficeZone['walk_target'] {
  if (type === 'meeting') return 'meeting'
  if (type === 'desk') return 'home'
  return 'center'
}

function defaultZoneShape(type: string): OfficeZone['shape'] {
  if (type === 'meeting' || type === 'desk') return undefined
  return 'circle'
}

function zoneShapeSize(zone: SpaceZone): { width: number; depth: number } {
  const radius = Math.max(0.5, zone.radius || 3.2)
  if (zone.shape === 'rect') {
    return { width: zone.width || radius * 2, depth: zone.depth || radius * 2 }
  }
  return { width: radius * 2, depth: radius * 2 }
}

const DEFAULT_FURNITURE_CATALOG: FurnitureDefinition[] = [
  { type: 'desk', label: '办公桌', category: 'desk', width: 1.75, depth: 0.95, height: 1.45, rotatable: true },
  { type: 'office_chair', label: '办公椅', category: 'chair', width: 0.6, depth: 0.62, height: 1.1, rotatable: true },
  { type: 'meeting_table', label: '会议长桌', category: 'meeting', width: 6.0, depth: 1.4, height: 0.72, rotatable: true },
  { type: 'meeting_chair', label: '会议椅', category: 'chair', width: 0.55, depth: 0.55, height: 0.95, rotatable: true },
  { type: 'plant', label: '绿植', category: 'plant', width: 0.55, depth: 0.55, height: 1.4, rotatable: false },
  { type: 'bookshelf', label: '书架', category: 'storage', width: 1.4, depth: 0.5, height: 2.1, rotatable: true },
  { type: 'coffee_bar', label: '茶水吧台', category: 'storage', width: 1.6, depth: 0.72, height: 1.3, rotatable: true },
  { type: 'lounge_sofa', label: '休息沙发', category: 'lounge', width: 2.0, depth: 0.9, height: 0.9, rotatable: true },
  { type: 'whiteboard', label: '白板', category: 'meeting', width: 2.1, depth: 0.08, height: 1.25, rotatable: true },
  { type: 'art', label: '装饰画', category: 'decor', width: 0.95, depth: 0.06, height: 0.7, rotatable: true },
]

const draft = ref<SpaceDraft>({
  floor: { width: 24, depth: 16 },
  workspace: { width: 44, depth: 26 },
  zones: [],
  furniture: [],
  furniture_catalog: DEFAULT_FURNITURE_CATALOG,
  character_models: [],
  status_zone_map: {},
  environment_theme: { preset: 'daylight' },
})

function normalizeDraft(value?: OfficeConfig): SpaceDraft {
  const source = value ? JSON.parse(JSON.stringify(value)) : {}
  const floor = source.floor || { width: 24, depth: 16 }
  const zones = Array.isArray(source.zones) ? source.zones : []
  const workspace = source.workspace || { width: 44, depth: 26 }
  const furniture = Array.isArray(source.furniture)
    ? source.furniture.map((item: OfficeFurnitureItem) => ({
        ...item,
        position: item.position || { x: 0, z: 0 },
        rotation_y: item.rotation_y ?? 0,
      }))
    : []
  const furnitureCatalog = Array.isArray(source.furniture_catalog) && source.furniture_catalog.length
    ? source.furniture_catalog
    : DEFAULT_FURNITURE_CATALOG
  return {
    floor: {
      width: Number(floor.width ?? 24),
      depth: Number(floor.depth ?? 16),
    },
    workspace: {
      width: Number(workspace.width ?? 44),
      depth: Number(workspace.depth ?? 26),
    },
    furniture,
    furniture_catalog: furnitureCatalog,
    character_models: Array.isArray(source.character_models) ? source.character_models : [],
    status_zone_map: { ...(source.status_zone_map || {}) },
    environment_theme: {
      preset: source.environment_theme?.preset || 'daylight',
      palette: { ...(source.environment_theme?.palette || {}) },
      props: { ...(source.environment_theme?.props || {}) },
      lighting: { ...(source.environment_theme?.lighting || {}) },
    },
    zones: zones.map((zone: OfficeZone): SpaceZone => ({
      ...zone,
      type: zone.type || 'desk',
      aliases: Array.isArray(zone.aliases)
        ? zone.aliases.map((alias) => String(alias).trim()).filter(Boolean)
        : [],
      walk_target: zone.walk_target || defaultWalkTarget(zone.type || 'desk'),
      shape: zone.shape || defaultZoneShape(zone.type || 'desk'),
      position: zone.position || { x: 0, z: 0 },
      radius: zone.radius,
      capacity: zone.capacity,
      slots: Array.isArray(zone.slots)
        ? zone.slots.map((slot): SpaceSlot => ({
            id: slot.id,
            role_key: slot.role_key ?? null,
            position: slot.position || { x: 0, z: 0 },
            rotation_y: slot.rotation_y ?? 0,
          }))
        : [],
    })),
  }
}

function syncDraft() {
  draft.value = normalizeDraft(props.officeConfig)
  selected.value = null
  drag.value = null
}

watch(() => props.officeConfig, syncDraft, { deep: true, immediate: true })

function meetingRoomSize(zone: SpaceZone): { width: number; depth: number } {
  if (zone.width && zone.depth) return { width: zone.width, depth: zone.depth }
  const xs = zone.slots.map((slot) => slot.position.x)
  const zs = zone.slots.map((slot) => slot.position.z)
  if (!xs.length || !zs.length) {
    const radius = Math.max(2.2, zone.radius || 3.2)
    return { width: radius * 2, depth: radius * 2 }
  }
  return {
    width: Math.max(...xs) - Math.min(...xs) + 2.7,
    depth: Math.max(...zs) - Math.min(...zs) + 2.7,
  }
}

function meetingTableSize(zone: SpaceZone): { width: number; depth: number } {
  const xs = zone.slots.map((slot) => slot.position.x)
  const zs = zone.slots.map((slot) => slot.position.z)
  if (!xs.length || !zs.length) {
    const radius = Math.max(2.2, zone.radius || 3.2)
    return { width: radius * 1.1, depth: radius * 1.1 }
  }
  const horizontal = Math.max(...xs) - Math.min(...xs) >= Math.max(...zs) - Math.min(...zs)
  const length = Math.max(2.0, (horizontal ? Math.max(...xs) - Math.min(...xs) : Math.max(...zs) - Math.min(...zs)) + 1.0)
  return horizontal ? { width: length, depth: 1.15 } : { width: 1.15, depth: length }
}

const officeExtents = computed(() => {
  const minX = -draft.value.workspace.width / 2
  const maxX = draft.value.workspace.width / 2
  const minZ = -draft.value.workspace.depth / 2
  const maxZ = draft.value.workspace.depth / 2
  const result = { minX, maxX, minZ, maxZ }
  for (const zone of draft.value.zones) {
    result.minX = Math.min(result.minX, zone.position.x)
    result.maxX = Math.max(result.maxX, zone.position.x)
    result.minZ = Math.min(result.minZ, zone.position.z)
    result.maxZ = Math.max(result.maxZ, zone.position.z)
    for (const slot of zone.slots) {
      result.minX = Math.min(result.minX, slot.position.x)
      result.maxX = Math.max(result.maxX, slot.position.x)
      result.minZ = Math.min(result.minZ, slot.position.z)
      result.maxZ = Math.max(result.maxZ, slot.position.z)
    }
  }
  for (const item of draft.value.furniture) {
    const size = furnitureSize(item)
    result.minX = Math.min(result.minX, item.position.x - size.width / 2)
    result.maxX = Math.max(result.maxX, item.position.x + size.width / 2)
    result.minZ = Math.min(result.minZ, item.position.z - size.depth / 2)
    result.maxZ = Math.max(result.maxZ, item.position.z + size.depth / 2)
  }
  return result
})

const viewBox = computed(() => {
  const ext = officeExtents.value
  const minX = planX(ext.minX) - pad
  const minY = planY(ext.maxZ) - pad
  const maxX = planX(ext.maxX) + pad
  const maxY = planY(ext.minZ) + pad
  return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`
})

const gridLines = computed(() => {
  const max = Math.max(draft.value.workspace.width, draft.value.workspace.depth)
  const lines: number[] = []
  for (let value = 2; value <= max; value += 2) lines.push(value)
  return lines
})

function planX(value: number): number {
  return pad + draft.value.workspace.width / 2 + value
}

function planY(value: number): number {
  return pad + draft.value.workspace.depth / 2 - value
}

function planDeltaX(slotX: number, zoneX: number): number {
  return slotX - zoneX
}

function planDeltaY(slotZ: number, zoneZ: number): number {
  return zoneZ - slotZ
}

function deskSlots(zone: SpaceZone): SpaceSlot[] {
  return zone.type === 'desk' ? zone.slots : []
}

function svgToConfig(point: { x: number; y: number }): { x: number; z: number } {
  return {
    x: point.x - pad - draft.value.workspace.width / 2,
    z: -(point.y - pad - draft.value.workspace.depth / 2),
  }
}

function svgPoint(event: PointerEvent): { x: number; y: number } {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const matrix = svg.getScreenCTM()
  if (!matrix) return { x: 0, y: 0 }
  const point = svg.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const transformed = point.matrixTransform(matrix.inverse())
  return { x: transformed.x, y: transformed.y }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function clampToFloorX(value: number): number {
  return clamp(value, -draft.value.floor.width / 2, draft.value.floor.width / 2)
}

function clampToFloorZ(value: number): number {
  return clamp(value, -draft.value.floor.depth / 2, draft.value.floor.depth / 2)
}

function clampToWorkspaceX(value: number): number {
  return clamp(value, -draft.value.workspace.width / 2, draft.value.workspace.width / 2)
}

function clampToWorkspaceZ(value: number): number {
  return clamp(value, -draft.value.workspace.depth / 2, draft.value.workspace.depth / 2)
}

function snap(value: number, step = 0.25): number {
  return Math.round(value / step) * step
}

function zoneTransform(zone: SpaceZone): string {
  return `translate(${planX(zone.position.x)} ${planY(zone.position.z)})`
}

function slotTransform(position: { x: number; z: number }): string {
  return `translate(${planX(position.x)} ${planY(position.z)})`
}

function furnitureDefinition(type: string): FurnitureDefinition | undefined {
  return draft.value.furniture_catalog.find((item) => item.type === type)
}

function furnitureSize(item: OfficeFurnitureItem): { width: number; depth: number } {
  const def = furnitureDefinition(item.type)
  return { width: def?.width || 1, depth: def?.depth || 1 }
}

function furnitureEffectiveSize(item: OfficeFurnitureItem): { width: number; depth: number } {
  const size = furnitureSize(item)
  const quarterTurns = Math.round(((item.rotation_y || 0) % (Math.PI * 2)) / (Math.PI / 2)) % 4
  return quarterTurns === 1 || quarterTurns === 3
    ? { width: size.depth, depth: size.width }
    : size
}

function clampFurnitureToWorkspace(item: OfficeFurnitureItem) {
  const size = furnitureEffectiveSize(item)
  const minX = -draft.value.workspace.width / 2 + size.width / 2
  const maxX = draft.value.workspace.width / 2 - size.width / 2
  const minZ = -draft.value.workspace.depth / 2 + size.depth / 2
  const maxZ = draft.value.workspace.depth / 2 - size.depth / 2
  item.position.x = clamp(item.position.x, Math.min(minX, maxX), Math.max(minX, maxX))
  item.position.z = clamp(item.position.z, Math.min(minZ, maxZ), Math.max(minZ, maxZ))
}

function furnitureLabel(item: OfficeFurnitureItem): string {
  return furnitureDefinition(item.type)?.label || item.type
}

function furnitureTransform(item: OfficeFurnitureItem): string {
  const rotation = -radToDeg(item.rotation_y || 0)
  return `translate(${planX(item.position.x)} ${planY(item.position.z)}) rotate(${rotation})`
}

function radToDeg(value: number): number {
  return value * 180 / Math.PI
}

const furnitureGroups = computed(() => {
  const labels: Record<string, string> = {
    desk: '办公桌',
    chair: '座椅',
    meeting: '会议',
    plant: '绿植',
    storage: '储物',
    lounge: '休息',
    decor: '装饰',
  }
  const groups: Array<{ category: string; label: string; items: FurnitureDefinition[] }> = []
  for (const item of draft.value.furniture_catalog) {
    let group = groups.find((entry) => entry.category === item.category)
    if (!group) {
      group = { category: item.category, label: labels[item.category] || item.category, items: [] }
      groups.push(group)
    }
    group.items.push(item)
  }
  return groups
})

function furnitureEmoji(type: string): string {
  const map: Record<string, string> = {
    desk: '🖥️',
    office_chair: '🪑',
    meeting_table: '📊',
    meeting_chair: '🪑',
    plant: '🪴',
    bookshelf: '📚',
    coffee_bar: '☕',
    lounge_sofa: '🛋️',
    whiteboard: '🧑‍🏫',
    art: '🖼️',
  }
  return map[type] || '🧩'
}

const meetingZones = computed(() => draft.value.zones.filter((zone) => zone.type === 'meeting'))

function meetingRoomBounds2D(zone: SpaceZone): { minX: number; maxX: number; minZ: number; maxZ: number } {
  const width = meetingRoomSize(zone).width
  const depth = meetingRoomSize(zone).depth
  return {
    minX: zone.position.x - width / 2,
    maxX: zone.position.x + width / 2,
    minZ: zone.position.z - depth / 2,
    maxZ: zone.position.z + depth / 2,
  }
}

function doorSideForZone(zone: SpaceZone): 'left' | 'right' | 'front' | 'back' {
  if (zone.door?.side) return zone.door.side
  const centerX = zone.position.x
  const centerZ = zone.position.z
  const outsideX = Math.abs(centerX) > draft.value.floor.width / 2
  const outsideZ = Math.abs(centerZ) > draft.value.floor.depth / 2
  if (!outsideX && !outsideZ) return 'left'
  if (Math.abs(centerX) - draft.value.floor.width / 2 >= Math.abs(centerZ) - draft.value.floor.depth / 2) {
    return centerX > 0 ? 'left' : 'right'
  }
  return centerZ > 0 ? 'back' : 'front'
}

function connectionRect(zone: SpaceZone): { x: number; y: number; width: number; height: number } | null {
  const bounds = meetingRoomBounds2D(zone)
  const doorSide = doorSideForZone(zone)
  const doorWidth = zone.door?.width || 1.4
  const doorOffset = zone.door?.offset || 0
  const floorMinX = -draft.value.floor.width / 2
  const floorMaxX = draft.value.floor.width / 2
  const floorMinZ = -draft.value.floor.depth / 2
  const floorMaxZ = draft.value.floor.depth / 2
  let from = 0
  let to = 0
  let horizontal = true

  if (doorSide === 'left') {
    from = floorMaxX
    to = bounds.minX
  } else if (doorSide === 'right') {
    from = bounds.maxX
    to = floorMinX
  } else if (doorSide === 'back') {
    horizontal = false
    from = floorMaxZ
    to = bounds.minZ
  } else {
    horizontal = false
    from = bounds.maxZ
    to = floorMinZ
  }

  if (to <= from) return null
  const length = to - from
  const centerX = horizontal ? (from + to) / 2 : zone.position.x + doorOffset
  const centerZ = horizontal ? zone.position.z + doorOffset : (from + to) / 2
  const width = horizontal ? length : doorWidth
  const depth = horizontal ? doorWidth : length
  return {
    x: planX(centerX - width / 2),
    y: planY(centerZ + depth / 2),
    width,
    height: depth,
  }
}

function getSelectedZone(): SpaceZone | null {
  if (!selected.value || !('zoneIndex' in selected.value)) return null
  return draft.value.zones[selected.value.zoneIndex] || null
}

const selectedZone = computed(() => getSelectedZone())

const selectedMeeting = computed(() => {
  const zone = selectedZone.value
  return zone?.type === 'meeting' ? zone : null
})

const selectedSlot = computed(() => {
  if (selected.value?.kind !== 'slot') return null
  const zone = selectedZone.value
  return zone?.slots[selected.value.slotIndex] || null
})

const selectedFurniture = computed(() => {
  if (selected.value?.kind !== 'furniture') return null
  return draft.value.furniture[selected.value.furnitureIndex] || null
})

const selectedTitle = computed(() => {
  if (selected.value?.kind === 'furniture') return '家具'
  const zone = selectedZone.value
  return zone?.label || (selected.value?.kind === 'slot' ? '工位' : '区域')
})

const themeProps = computed(() => draft.value.environment_theme.props || {})

function isSelectedSlot(zoneIndex: number, slotIndex: number): boolean {
  return selected.value?.kind === 'slot' && selected.value.zoneIndex === zoneIndex && selected.value.slotIndex === slotIndex
}

function isSelectedFurniture(furnitureIndex: number): boolean {
  return selected.value?.kind === 'furniture' && selected.value.furnitureIndex === furnitureIndex
}

function isSelectedZone(zoneIndex: number): boolean {
  if (!selected.value || !('zoneIndex' in selected.value)) return false
  return selected.value.zoneIndex === zoneIndex
}

function deselect() {
  selected.value = null
}

function zoneTypeLabel(type: string): string {
  return ZONE_TYPE_LABELS[type] || type
}

function zoneWalkTargetLabel(value?: string): string {
  if (!value) return '未设置'
  return WALK_TARGET_LABELS[value] || value
}

function selectZone(zoneIndex: number) {
  if (!draft.value.zones[zoneIndex]) return
  selected.value = { kind: 'zone', zoneIndex }
}

function addZone() {
  const zoneIndex = draft.value.zones.length
  const id = `zone_${Date.now()}_${zoneIndex}`
  draft.value.zones.push({
    id,
    type: 'public',
    label: '新区域',
    aliases: [],
    walk_target: 'center',
    shape: 'circle',
    position: { x: 0, z: 0 },
    radius: 3.2,
    slots: [],
  })
  selected.value = { kind: 'zone', zoneIndex }
}

function deleteSelectedZone() {
  if (!selected.value || !('zoneIndex' in selected.value)) return
  const zone = draft.value.zones[selected.value.zoneIndex]
  if (!zone) return
  if (zone.type === 'desk' && draft.value.zones.filter((item) => item.type === 'desk').length <= 1) {
    message.warning('至少保留一个工位区')
    return
  }
  draft.value.zones.splice(selected.value.zoneIndex, 1)
  if (draft.value.status_zone_map) {
    for (const [key, value] of Object.entries(draft.value.status_zone_map)) {
      if (value === zone.id) delete draft.value.status_zone_map[key]
    }
  }
  selected.value = null
}

function addFurniture(type: string) {
  const def = furnitureDefinition(type)
  if (!def) return
  const id = `furniture_${Date.now()}_${draft.value.furniture.length}`
  draft.value.furniture.push({
    id,
    type,
    position: { x: 0, z: 0 },
    rotation_y: 0,
  })
  selected.value = { kind: 'furniture', furnitureIndex: draft.value.furniture.length - 1 }
}

function startFurnitureDrag(event: PointerEvent, furnitureIndex: number) {
  const item = draft.value.furniture[furnitureIndex]
  if (!item) return
  const config = svgToConfig(svgPoint(event))
  selected.value = { kind: 'furniture', furnitureIndex }
  drag.value = {
    kind: 'furniture',
    furnitureIndex,
    offset: {
      x: config.x - item.position.x,
      z: config.z - item.position.z,
    },
  }
}

function rotateSelectedFurniture() {
  const item = selectedFurniture.value
  if (!item) return
  item.rotation_y = (item.rotation_y || 0) + Math.PI / 2
}

function deleteSelectedFurniture() {
  if (selected.value?.kind !== 'furniture') return
  draft.value.furniture.splice(selected.value.furnitureIndex, 1)
  selected.value = null
}

function startSlotDrag(event: PointerEvent, zoneIndex: number, slotIndex: number) {
  const zone = draft.value.zones[zoneIndex]
  const slot = zone?.slots[slotIndex]
  if (!zone || !slot) return
  const config = svgToConfig(svgPoint(event))
  selected.value = { kind: 'slot', zoneIndex, slotIndex }
  drag.value = {
    kind: 'slot',
    zoneIndex,
    slotIndex,
    offset: {
      x: config.x - slot.position.x,
      z: config.z - slot.position.z,
    },
  }
}

function startMeetingDrag(event: PointerEvent, zoneIndex: number) {
  const zone = draft.value.zones[zoneIndex]
  if (!zone) return
  const config = svgToConfig(svgPoint(event))
  selected.value = { kind: 'meeting', zoneIndex }
  drag.value = {
    kind: 'meeting',
    zoneIndex,
    offset: {
      x: config.x - zone.position.x,
      z: config.z - zone.position.z,
    },
  }
}

function startZoneDrag(event: PointerEvent, zoneIndex: number) {
  const zone = draft.value.zones[zoneIndex]
  if (!zone) return
  const config = svgToConfig(svgPoint(event))
  selected.value = { kind: 'zone', zoneIndex }
  drag.value = {
    kind: 'zone',
    zoneIndex,
    offset: {
      x: config.x - zone.position.x,
      z: config.z - zone.position.z,
    },
  }
}

function onPointerMove(event: PointerEvent) {
  if (!drag.value) return
  const config = svgToConfig(svgPoint(event))
  const current = drag.value

  if (current.kind === 'slot') {
    const zone = draft.value.zones[current.zoneIndex]
    const slot = zone?.slots[current.slotIndex]
    if (!zone || !slot) return
    slot.position.x = clampToFloorX(config.x - current.offset.x)
    slot.position.z = clampToFloorZ(config.z - current.offset.z)
    return
  }

  if (current.kind === 'furniture') {
    const item = draft.value.furniture[current.furnitureIndex]
    if (!item) return
    const size = furnitureEffectiveSize(item)
    const minX = -draft.value.workspace.width / 2 + size.width / 2
    const maxX = draft.value.workspace.width / 2 - size.width / 2
    const minZ = -draft.value.workspace.depth / 2 + size.depth / 2
    const maxZ = draft.value.workspace.depth / 2 - size.depth / 2
    item.position.x = snap(clamp(config.x - current.offset.x, Math.min(minX, maxX), Math.max(minX, maxX)))
    item.position.z = snap(clamp(config.z - current.offset.z, Math.min(minZ, maxZ), Math.max(minZ, maxZ)))
    return
  }

  const zone = draft.value.zones[current.zoneIndex]
  if (!zone) return
  const nextX = clampToWorkspaceX(config.x - current.offset.x)
  const nextZ = clampToWorkspaceZ(config.z - current.offset.z)
  const deltaX = nextX - zone.position.x
  const deltaZ = nextZ - zone.position.z
  zone.position.x = nextX
  zone.position.z = nextZ
  for (const slot of zone.slots) {
    slot.position.x = clampToWorkspaceX(slot.position.x + deltaX)
    slot.position.z = clampToWorkspaceZ(slot.position.z + deltaZ)
  }
}

function onPointerUp() {
  drag.value = null
}

function onPointerCancel() {
  drag.value = null
}

const validationIssues = computed(() => {
  const issues: string[] = []
  const floorMinX = -draft.value.floor.width / 2
  const floorMaxX = draft.value.floor.width / 2
  const floorMinZ = -draft.value.floor.depth / 2
  const floorMaxZ = draft.value.floor.depth / 2
  const workspaceMinX = -draft.value.workspace.width / 2
  const workspaceMaxX = draft.value.workspace.width / 2
  const workspaceMinZ = -draft.value.workspace.depth / 2
  const workspaceMaxZ = draft.value.workspace.depth / 2

  for (const zone of meetingZones.value) {
    const bounds = meetingRoomBounds2D(zone)
    const overlapsOffice =
      bounds.maxX > floorMinX + 0.15 &&
      bounds.minX < floorMaxX - 0.15 &&
      bounds.maxZ > floorMinZ + 0.15 &&
      bounds.minZ < floorMaxZ - 0.15
    if (overlapsOffice) issues.push('会议室不能叠在办公区上，请拖到办公区外侧。')
  }

  for (const item of draft.value.furniture) {
    const size = furnitureEffectiveSize(item)
    const minX = item.position.x - size.width / 2
    const maxX = item.position.x + size.width / 2
    const minZ = item.position.z - size.depth / 2
    const maxZ = item.position.z + size.depth / 2
    if (minX < workspaceMinX || maxX > workspaceMaxX || minZ < workspaceMinZ || maxZ > workspaceMaxZ) {
      issues.push(`家具“${furnitureLabel(item)}”超出画布，请拖回画布内。`)
    }
  }

  if (!draft.value.zones.some((zone) => zone.type === 'desk')) {
    issues.push('至少保留一个工位区，AI 同事才能回到自己的座位。')
  }

  for (const zone of draft.value.zones) {
    if (zone.type !== 'desk') continue
    for (const slot of zone.slots) {
      if (
        slot.position.x < floorMinX ||
        slot.position.x > floorMaxX ||
        slot.position.z < floorMinZ ||
        slot.position.z > floorMaxZ
      ) {
        issues.push('工位超出办公区，请拖回办公区。')
        break
      }
    }
  }

  return issues
})

async function save() {
  let clampedFurniture = false
  for (const item of draft.value.furniture) {
    const size = furnitureEffectiveSize(item)
    const minX = item.position.x - size.width / 2
    const maxX = item.position.x + size.width / 2
    const minZ = item.position.z - size.depth / 2
    const maxZ = item.position.z + size.depth / 2
    const workspaceMinX = -draft.value.workspace.width / 2
    const workspaceMaxX = draft.value.workspace.width / 2
    const workspaceMinZ = -draft.value.workspace.depth / 2
    const workspaceMaxZ = draft.value.workspace.depth / 2
    if (minX < workspaceMinX || maxX > workspaceMaxX || minZ < workspaceMinZ || maxZ > workspaceMaxZ) {
      clampFurnitureToWorkspace(item)
      clampedFurniture = true
    }
  }
  if (clampedFurniture) message.info('已将越界家具自动移回画布内')

  if (validationIssues.value.length) {
    message.error(validationIssues.value[0])
    return
  }
  saving.value = true
  try {
    await officeApi.updateLayout({ office: draft.value })
    message.success('空间布局已保存')
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '空间布局保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerCancel)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerCancel)
})
defineExpose({ save })
</script>

<style scoped>
.space-editor {
  padding: 16px;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--cpq-bg-primary);
  color: var(--cpq-text-primary);
}

.se-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.se-toolbar h3 {
  margin: 0;
  font-size: 18px;
  color: var(--cpq-text-primary);
}

.se-toolbar p {
  margin: 4px 0 0;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.se-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.se-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 320px;
  gap: 12px;
}

.se-library,
.se-props {
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.se-library-tip {
  margin-bottom: 10px;
  color: var(--cpq-text-muted);
  font-size: 11px;
  line-height: 1.5;
}

.se-furniture-group {
  margin-bottom: 12px;
}

.se-furniture-group-title {
  margin-bottom: 6px;
  color: var(--cpq-text-secondary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .06em;
  text-transform: uppercase;
}

.se-furniture-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  padding: 7px 8px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 9px;
  background: var(--cpq-bg-card);
  color: var(--cpq-text-primary);
  cursor: pointer;
  text-align: left;
  transition: border-color .16s ease, transform .16s ease, box-shadow .16s ease;
}

.se-furniture-item:hover {
  border-color: var(--cpq-accent-primary-light);
  box-shadow: var(--cpq-shadow-md);
  transform: translateY(-1px);
}

.se-furniture-emoji {
  font-size: 18px;
  line-height: 1;
}

.se-furniture-label {
  font-size: 12px;
}

.se-plan-panel {
  min-width: 0;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 14px;
  background: var(--cpq-bg-card);
  overflow: hidden;
  box-shadow: var(--cpq-shadow-lg);
}

.se-plan {
  flex: 1;
  width: 100%;
  min-height: 0;
  touch-action: none;
  cursor: default;
  background: var(--cpq-bg-secondary);
}

.se-workspace {
  fill: var(--cpq-bg-tertiary);
  stroke: var(--cpq-border-primary);
  stroke-width: .12;
  stroke-dasharray: .5 .35;
}

.se-floor {
  fill: var(--cpq-bg-card);
  stroke: var(--cpq-border-primary);
  stroke-width: .16;
  filter: drop-shadow(0 3px 6px var(--cpq-shadow-color-soft));
}

.se-area-label {
  fill: var(--cpq-text-muted);
  font-size: .62px;
  font-weight: 700;
  letter-spacing: .08em;
  pointer-events: none;
}

.se-grid-line {
  stroke: var(--cpq-grid-line);
  stroke-width: .07;
  pointer-events: none;
}

.meeting-carpet {
  fill: var(--cpq-overlay-a10);
  stroke: var(--cpq-accent-primary-light);
  stroke-width: .12;
  cursor: move;
  opacity: .9;
}

.meeting-table {
  fill: var(--cpq-bg-input);
  stroke: var(--cpq-border-light);
  stroke-width: .09;
  cursor: move;
}

.meeting-slot {
  fill: var(--cpq-text-muted);
  stroke: var(--cpq-bg-card);
  stroke-width: .08;
  cursor: move;
}

.meeting-slot.selected {
  fill: var(--cpq-accent-primary);
}

.desk-slot {
  cursor: move;
}

.desk-body {
  fill: var(--cpq-bg-input);
  stroke: var(--cpq-border-light);
  stroke-width: .12;
}

.desk-body.selected {
  fill: var(--cpq-accent-primary);
  stroke: var(--cpq-accent-primary-light);
  stroke-width: .2;
}

.desk-direction {
  stroke: var(--cpq-color-success);
  stroke-width: .13;
  stroke-linecap: round;
  pointer-events: none;
}

.se-door-corridor {
  fill: var(--cpq-bg-card);
  stroke: var(--cpq-accent-primary-light);
  stroke-width: .08;
  pointer-events: none;
}

.furniture-item {
  cursor: move;
}

.furniture-body {
  fill: var(--cpq-bg-card);
  stroke: var(--cpq-border-primary);
  stroke-width: .13;
  filter: drop-shadow(0 2px 3px var(--cpq-shadow-color-soft));
}

.furniture-body.selected {
  fill: var(--cpq-bg-selected);
  stroke: var(--cpq-accent-primary);
  stroke-width: .22;
}

.furniture-label {
  fill: var(--cpq-text-secondary);
  font-size: .34px;
  pointer-events: none;
}

.se-plan-hint {
  position: absolute;
  left: 12px;
  bottom: 10px;
  padding: 6px 9px;
  border-radius: 8px;
  color: var(--cpq-text-secondary);
  font-size: 11px;
  background: var(--cpq-glass-2-bg);
  pointer-events: none;
}

.se-plan-warning {
  position: absolute;
  left: 12px;
  top: 10px;
  max-width: calc(100% - 24px);
  padding: 7px 10px;
  border-radius: 8px;
  color: var(--cpq-accent-danger);
  font-size: 12px;
  background: var(--cpq-overlay-danger10);
  border: 1px solid var(--cpq-accent-danger);
}

.se-card {
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 12px;
  padding: 12px;
  background: var(--cpq-bg-card);
}

.se-card-title {
  margin-bottom: 10px;
  color: var(--cpq-text-secondary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.se-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
  color: var(--cpq-text-muted);
  font-size: 11px;
}

.se-field:last-child {
  margin-bottom: 0;
}

.se-switch {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.se-switch span {
  flex: 1;
}

.se-empty-props {
  padding: 16px 12px;
  border: 1px dashed var(--cpq-border-light);
  border-radius: 12px;
  color: var(--cpq-text-muted);
  font-size: 12px;
  text-align: center;
}

.se-zone-empty {
  margin-bottom: 10px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.se-zone-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  padding: 7px 8px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 9px;
  background: var(--cpq-bg-card);
  color: var(--cpq-text-primary);
  cursor: pointer;
  text-align: left;
  transition: border-color .16s ease, box-shadow .16s ease;
}

.se-zone-item:hover {
  border-color: var(--cpq-accent-primary-light);
  box-shadow: var(--cpq-shadow-md);
}

.se-zone-item.selected {
  border-color: var(--cpq-accent-primary);
  box-shadow: 0 0 0 1px var(--cpq-accent-primary);
}

.se-zone-name {
  font-size: 12px;
  font-weight: 700;
}

.se-zone-meta {
  color: var(--cpq-text-muted);
  font-size: 10px;
  white-space: nowrap;
}

.zone-footprint {
  cursor: pointer;
}

.zone-footprint-shape {
  fill: var(--cpq-overlay-a10);
  stroke: var(--cpq-accent-primary-light);
  stroke-width: .12;
  stroke-dasharray: .4 .3;
}

.zone-footprint-shape.selected {
  fill: var(--cpq-bg-selected);
  stroke: var(--cpq-accent-primary);
  stroke-width: .22;
}

.zone-footprint-label {
  fill: var(--cpq-text-secondary);
  font-size: .42px;
  pointer-events: none;
}

.se-furniture-name {
  margin-bottom: 10px;
  color: var(--cpq-text-primary);
  font-size: 13px;
  font-weight: 700;
}

.se-prop-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

@media (max-width: 1100px) {
  .se-layout {
    grid-template-columns: 190px minmax(0, 1fr) 290px;
  }
}

@media (max-width: 900px) {
  .se-layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(320px, 1fr) auto;
  }

  .se-library,
  .se-props {
    max-height: 280px;
  }
}
</style>
