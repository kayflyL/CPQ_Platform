<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import draggable from 'vuedraggable'
import type { PortalSheetRow } from '@/api/portal'
import { kpPartsApi, type KpPart } from '@/api/serverConfig'
import { formatPrice as money } from '@/utils/quoteCommon'

const props = withDefaults(defineProps<{
  canEdit?: boolean
  canEditCost?: boolean
  showCostColumns?: boolean
  showDrag?: boolean
  groupLabel?: string
  defaultCategories?: string[]
}>(), {
  canEdit: true,
  canEditCost: false,
  showCostColumns: false,
  showDrag: true,
  groupLabel: 'KP',
  defaultCategories: () => [],
})

const rows = defineModel<PortalSheetRow[]>('rows', { default: () => [] })

const kpCategories = ref<{ id: number; name: string }[]>([])
const kpCatalog = ref<Record<string, KpPart[]>>({})
const kpCatalogLoading = ref(false)
let kpCatalogLoaded = false

const rowKeys = new WeakMap<object, string>()
let rowKeySeq = 1
function rowKeyFor(row: PortalSheetRow) {
  let key = rowKeys.get(row)
  if (!key) {
    key = `row-${rowKeySeq++}`
    rowKeys.set(row, key)
  }
  return key
}

function blankKpRow(partCategory = ''): PortalSheetRow {
  return {
    category: 'Key Parts',
    part_category: partCategory,
    catalogue: '',
    description: '',
    qty: 1,
    base_price: 0,
    final_price: 0,
    profit_margin: 10,
    currency: 'RMB',
    note: '',
  }
}

async function loadKpCatalog() {
  if (kpCatalogLoaded) return
  kpCatalogLoading.value = true
  try {
    const cats = await kpPartsApi.categories()
    kpCategories.value = cats
    const results = await Promise.all(cats.map((c) => kpPartsApi.listByCategory(c.id)))
    const catalog: Record<string, KpPart[]> = {}
    cats.forEach((c, i) => { catalog[c.name] = results[i] || [] })
    kpCatalog.value = catalog
    kpCatalogLoaded = true
  } catch (error) {
    console.warn('加载配件库目录失败', error)
  } finally {
    kpCatalogLoading.value = false
  }
}

const kpCategoryOptions = computed(() => kpCategories.value.map((c) => ({ value: c.name, label: c.name })))
const kpAllParts = computed(() => kpCategories.value.flatMap((c) => kpCatalog.value[c.name] || []))

function kpPartsFor(category?: string): KpPart[] {
  if (!category) return kpAllParts.value
  return kpCatalog.value[category] || []
}

function kpCatalogueOptions(category?: string) {
  return kpPartsFor(category).map((part) => ({
    label: category ? part.name : `${part.category} · ${part.name}`,
    value: part.name,
    part,
  }))
}

function kpCatalogueFilter(input: string, option: any) {
  const text = [option?.value, option?.part?.pn, option?.part?.category]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return text.includes((input || '').toLowerCase())
}

function kpPartByName(category: string | undefined, name: string) {
  return kpPartsFor(category).find((part) => part.name === name)
}

function onKpCatalogueChange(row: PortalSheetRow, value: string | undefined) {
  const name = value || ''
  row.catalogue = name
  if (!name) return
  const part = kpPartByName(row.part_category, name) || kpPartByName(undefined, name)
  if (!part) return
  row.part_category = part.category
  if (part.unit_price != null) row.base_price = part.unit_price
}

function onKpCategoryChange(row: PortalSheetRow, value: string | undefined) {
  row.part_category = value || ''
  const parts = kpPartsFor(row.part_category)
  if (row.catalogue && parts.length && !parts.some((part) => part.name === row.catalogue)) {
    row.catalogue = ''
    row.base_price = 0
  }
}

function rowCost(row: PortalSheetRow) {
  return Number(row.base_price || 0) * Number(row.qty || 0)
}

function removeRow(idx: number) {
  rows.value.splice(idx, 1)
}

onMounted(() => {
  loadKpCatalog()
  if (!rows.value.length && props.defaultCategories.length) {
    rows.value = props.defaultCategories.map((cat) => blankKpRow(cat))
  }
})
</script>

<template>
  <draggable
    v-if="rows.length"
    v-model="rows"
    tag="tbody"
    :item-key="rowKeyFor"
    handle=".sheet-drag"
    :animation="180"
    :disabled="!canEdit || !showDrag"
    class="sheet-tbody"
  >
    <template #item="{ element: row, index: idx }">
      <tr class="sheet-row" :class="{ 'sheet-group-start-row': idx === 0 }">
        <td class="sheet-group">{{ idx === 0 ? groupLabel : '' }}</td>
        <td class="sheet-cell">
          <div class="sheet-cell-inline">
            <span v-if="canEdit && showDrag" class="sheet-drag" title="拖拽排序">⠿</span>
            <div class="sheet-cell-main">
              <a-auto-complete
                v-if="canEdit"
                v-model:value="row.part_category"
                :options="kpCategoryOptions"
                :default-active-first-option="false"
                :allow-clear="false"
                placeholder="选择或输入类别"
                style="width: 100%"
                @select="(value: string) => onKpCategoryChange(row, value)"
              />
              <span v-else class="sheet-plain">{{ row.part_category || '—' }}</span>
            </div>
            <a-button v-if="canEdit" type="text" danger size="small" class="sheet-row-del" @click="removeRow(idx)">×</a-button>
          </div>
        </td>
        <td class="sheet-cell">
          <a-auto-complete
            v-if="canEdit"
            v-model:value="row.catalogue"
            :options="kpCatalogueOptions(row.part_category)"
            :filter-option="kpCatalogueFilter"
            :default-active-first-option="false"
            :allow-clear="false"
            placeholder="选择或输入配件"
            style="width: 100%"
            @select="(value: string) => onKpCatalogueChange(row, value)"
          />
          <span v-else class="sheet-plain sheet-wrap">{{ row.catalogue || '—' }}</span>
        </td>
        <td class="sheet-cell sheet-qty">
          <a-input-number :controls="false" v-if="canEdit" v-model:value="row.qty" :min="0" :precision="0" class="sheet-input" />
          <span v-else class="sheet-plain sheet-num">{{ row.qty || 0 }}</span>
        </td>
        <template v-if="showCostColumns">
          <td class="sheet-cell sheet-cost">
            <a-input-number :controls="false" v-if="canEditCost" v-model:value="row.base_price" :min="0" :precision="2" class="sheet-input" />
            <span v-else class="sheet-plain sheet-num">{{ money(row.base_price) }}</span>
          </td>
          <td class="sheet-cell sheet-cost sheet-derived">¥{{ money(rowCost(row)) }}</td>
          <td class="sheet-cell">
            <a-input v-if="canEditCost" v-model:value="row.note" class="sheet-input" placeholder="备注" />
            <span v-else class="sheet-plain sheet-wrap">{{ row.note || '—' }}</span>
          </td>
        </template>
      </tr>
    </template>
  </draggable>
</template>

<style scoped>
.sheet-group {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--cpq-bg-tertiary);
  color: var(--cpq-accent-primary);
  text-align: center;
  font-size: 11px;
  font-weight: 650;
  vertical-align: middle;
  border-bottom: 0;
}
.sheet-row.sheet-group-start-row .sheet-group {
  box-shadow: inset 0 1px 0 var(--cpq-border-primary);
}
.sheet-cell {
  height: 36px;
  padding: 0;
  transition: background 0.15s ease;
}
.sheet-tbody td {
  border-right: 1px solid var(--cpq-border-secondary);
  border-bottom: 1px solid var(--cpq-border-secondary);
  text-align: left;
  vertical-align: middle;
}
.sheet-tbody td:last-child {
  border-right: 0;
}
.sheet-row:hover td {
  background: var(--cpq-overlay-w4);
}
.sheet-cell:focus-within {
  background: var(--cpq-overlay-w4);
  box-shadow: inset 0 -1px 0 var(--cpq-accent-primary);
}
.sheet-drag {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  cursor: grab;
  color: var(--cpq-text-muted);
  font-size: 14px;
  user-select: none;
}
.sheet-drag:active {
  cursor: grabbing;
}
.sheet-cell-inline {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.sheet-cell-main {
  flex: 1;
  min-width: 0;
}
.sheet-row-del {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.sheet-row:hover .sheet-row-del,
.sheet-cell:focus-within .sheet-row-del {
  opacity: 1;
}
.sheet-input {
  width: 100%;
}
.sheet-plain {
  display: block;
  padding: 0 8px;
  line-height: 36px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sheet-wrap {
  padding: 8px;
  line-height: 1.45;
  white-space: normal;
}
.sheet-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.sheet-qty,
.sheet-cost {
  text-align: right;
}
.sheet-derived {
  padding: 0 8px;
  color: var(--cpq-accent-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}
</style>
