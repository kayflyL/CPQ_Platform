<script setup lang="ts">
/** 统一选料器 PartPicker —— a-select 封装，下拉里卡片化选项 + 搜索 + 规格摘要。
 *  接收父组件已归一化的 PickerItem[]（不内嵌 API，KP/L6 两源由 usePartAdapter 映射后传入）。
 *  契约：update:modelValue 只回传 pn（单选字符串 / 多选字符串数组），不回传对象——
 *  这是 L6 产出契约的兜底，确保 setOverride(key, pn) 调用签名不变。 */
import { computed } from 'vue'
import { specSummary } from '@/constants/partSpecFields'
import type { PickerItem } from '@/types/picker'

const props = withDefaults(defineProps<{
  items: PickerItem[]
  modelValue?: string | string[] | undefined
  multiple?: boolean
  searchable?: boolean
  placeholder?: string
  size?: 'small' | 'middle' | 'large'
  allowClear?: boolean
  disabled?: boolean
}>(), {
  modelValue: undefined,
  multiple: false,
  searchable: true,
  placeholder: '请选择',
  size: 'middle',
  allowClear: false,
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: string | string[]): void
  (e: 'select', item: PickerItem | PickerItem[] | undefined): void
}>()

const options = computed(() =>
  (props.items || []).map(p => ({ label: p.name || p.pn, value: p.pn, item: p }))
)

function priceFmt(n?: number) { return n == null ? '' : '¥' + n.toLocaleString() }
function summaryOf(it?: PickerItem) { return it ? specSummary(it.specs, it.category) : '' }

function filterOption(input: string, option: any) {
  if (!props.searchable) return true
  const q = (input || '').toLowerCase().trim()
  if (!q) return true
  const it: PickerItem = option?.item
  if (!it) return false
  return (
    (it.pn || '').toLowerCase().includes(q) ||
    (it.name || '').toLowerCase().includes(q) ||
    (it.sub_type || '').toLowerCase().includes(q) ||
    summaryOf(it).toLowerCase().includes(q)
  )
}

function onChange(value: any, option: any) {
  emit('update:modelValue', value) // 单选 pn / 多选 pn[]
  if (props.multiple) {
    const arr = Array.isArray(option) ? option.map((o: any) => o?.item).filter(Boolean) : []
    emit('select', arr as PickerItem[])
  } else {
    emit('select', option?.item as PickerItem | undefined)
  }
}
</script>

<template>
  <a-select
    :value="modelValue"
    :mode="multiple ? 'multiple' : undefined"
    :options="options"
    :placeholder="placeholder"
    :size="size"
    :allow-clear="allowClear"
    :disabled="disabled"
    :show-search="searchable"
    :filter-option="filterOption"
    option-label-prop="label"
    popup-class-name="pp-dropdown"
    style="width: 100%"
    @change="onChange"
  >
    <template #option="opt">
      <slot name="option" :item="opt.item">
        <div class="pp-opt">
          <div class="pp-opt-row">
            <span class="pp-opt-name">{{ opt.item.name }}</span>
            <span v-if="opt.item.unit_price != null" class="pp-opt-price">{{ priceFmt(opt.item.unit_price) }}</span>
          </div>
          <div class="pp-opt-sub">
            <span v-if="summaryOf(opt.item)" class="pp-opt-spec">{{ summaryOf(opt.item) }}</span>
            <span class="pp-opt-pn">{{ opt.item.pn }}</span>
          </div>
        </div>
      </slot>
    </template>
    <template v-if="!options.length" #notFoundContent>
      <slot name="empty">
        <span class="pp-empty">暂无可选料号</span>
      </slot>
    </template>
  </a-select>
</template>

<!-- 下拉面板 teleport 到 body，必须非 scoped；用 .pp-dropdown 前缀限定，不污染全局 -->
<style>
.pp-dropdown .pp-opt { padding: 4px 2px; line-height: 1.4; }
.pp-dropdown .pp-opt-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.pp-dropdown .pp-opt-name { font-size: 13px; color: var(--cpq-text-primary, #E8ECEF); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pp-dropdown .pp-opt-price { font-size: 12px; color: var(--cpq-accent-primary, #00F5D4); font-weight: 600; white-space: nowrap; }
.pp-dropdown .pp-opt-sub { display: flex; gap: 8px; align-items: center; margin-top: 2px; font-size: 11px; }
.pp-dropdown .pp-opt-spec { color: var(--cpq-text-secondary, #9BA1AA); }
.pp-dropdown .pp-opt-pn { color: var(--cpq-text-muted, #6E7582); margin-left: auto; }
.pp-dropdown .pp-empty { color: var(--cpq-text-muted, #6E7582); font-size: 12px; }
</style>
