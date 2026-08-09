<script setup lang="ts">
/** 单个 BOM 规则 source 编辑器（desc 或 qty）。
 *  设计原则：控件自解释，不靠小字说明 ——
 *   · kind 下拉用大白话（存储值不变）
 *   · 料号品类 category 从下拉选（不再自由输入）
 *   · 模板拼接：点选变量插入 + 实时渲染预览（用户不写 ${} 语法）
 *   · 结构计数 scope 按行类型限定（io_slot 行只给 io_slot 等） */
import { computed, ref, nextTick } from 'vue'
import type { DescSource, QtySource } from '@/api/serverConfig'

defineOptions({ name: 'BomRuleSourceEditor' })

const props = defineProps<{
  modelValue: DescSource | QtySource | undefined
  mode: 'desc' | 'qty'
  rowType?: string          // 当前行类型：用于 struct_count scope 限定
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: DescSource | QtySource): void }>()

/** kind 下拉：大白话 label，存储值不变 */
const DESC_KINDS = [
  { value: 'fixed', label: '固定文字' },
  { value: 'part_field', label: '取料号字段' },
  { value: 'template', label: '模板拼接' },
  { value: 'struct_count', label: '按结构自动生成' },
  { value: 'config_value', label: '取配置参数' },
  { value: 'manual', label: '手动填写' },
]
const QTY_KINDS = [
  { value: 'fixed', label: '固定数量' },
  { value: 'part_quantity', label: '取料号数量' },
  { value: 'config_calc', label: '按配置数量' },
  { value: 'manual', label: '手动填写' },
]
/** 底盘件品类下拉：系统真实存在的品类，用户不再猜 */
const CATEGORY_OPTIONS = [
  { value: 'heatsink', label: 'heatsink 散热器' },
  { value: 'fan', label: 'fan 风扇' },
  { value: 'rail', label: 'rail 滑轨/导轨' },
  { value: 'backplane', label: 'backplane 背板' },
  { value: 'psu', label: 'psu 电源' },
  { value: 'cable', label: 'cable 线缆' },
]
/** 模板拼接变量：中文标注，点选插入 */
const TEMPLATE_VARS = [
  { key: 'bays', label: 'bays 盘位数' },
  { key: 'form', label: 'form 机箱形态' },
  { key: 'series', label: 'series 系列' },
  { key: 'bp_type', label: 'bp_type 背板类型' },
  { key: 'bp_type_desc', label: 'bp_type_desc 背板类型描述' },
  { key: 'psu_qty', label: 'psu_qty 电源数量' },
  { key: 'psu_wattage', label: 'psu_wattage 电源功率' },
  { key: 'psu_name', label: 'psu_name 电源型号' },
  { key: 'gpu_qty', label: 'gpu_qty GPU 数量' },
  { key: 'gpu_cable_qty', label: 'gpu_cable_qty GPU 线数量' },
]
/** 结构计数 scope：大白话 + 按行类型限定可选范围 */
const SCOPE_OPTIONS = [
  { value: 'io_slot', label: '该槽位 riser 规格（数据驱动）' },
  { value: 'rear_all', label: '后面板汇总（GPU+NVMe+IO）' },
  { value: 'gpu_direct', label: '仅 GPU 直连' },
  { value: 'front_cables', label: '前面板线缆（按盘介质）' },
]
const CONFIG_KEYS_DESC = [
  { key: 'bays', label: 'bays 盘位数' },
  { key: 'form', label: 'form 机箱形态' },
  { key: 'series', label: 'series 系列' },
  { key: 'bp_type', label: 'bp_type 背板类型' },
  { key: 'psu_qty', label: 'psu_qty 电源数量' },
  { key: 'psu_wattage', label: 'psu_wattage 电源功率' },
  { key: 'psu_name', label: 'psu_name 电源型号' },
  { key: 'gpu_qty', label: 'gpu_qty GPU 数量' },
  { key: 'gpu_cable_qty', label: 'gpu_cable_qty GPU 线数量' },
  { key: 'gpu_power_cord_desc', label: 'gpu_power_cord_desc GPU 供电线描述' },
  { key: 'cable_desc', label: 'cable_desc 线缆汇总' },
]
const CONFIG_KEYS_QTY = [
  { key: 'psu_qty', label: 'psu_qty 电源数量' },
  { key: 'gpu_cable_qty', label: 'gpu_cable_qty GPU 线数量' },
]
const PART_FIELDS = [
  { value: 'name', label: 'name 名称' },
  { value: 'pn', label: 'pn 料号' },
  { value: 'specs.bt', label: 'specs.bt 背板类型' },
  { value: 'specs.kind', label: 'specs.kind 种类' },
  { value: 'specs.model', label: 'specs.model 型号' },
]

const kinds = computed(() => props.mode === 'desc' ? DESC_KINDS : QTY_KINDS)
const src = computed<any>({
  get: () => props.modelValue || { kind: 'manual' },
  set: (v) => emit('update:modelValue', v),
})

/** struct_count 可选 scope：按行类型限定 */
const allowedScopes = computed(() => {
  if (props.rowType === 'io_slot') return SCOPE_OPTIONS.filter(s => s.value === 'io_slot')
  if (props.rowType === 'rear_summary') return SCOPE_OPTIONS.filter(s => s.value === 'rear_all' || s.value === 'gpu_direct')
  return SCOPE_OPTIONS
})

/** 模板拼接渲染预览：用演示值替换 ${var}，缺变量原样显示 */
const DEMO_VARS: Record<string, string> = {
  bays: '24', form: '2U', series: 'R760', bp_type: 'tri', bp_type_desc: 'SATA/SAS/NVMe',
  psu_qty: '2', psu_wattage: '2000', psu_name: '2000W', gpu_qty: '2', gpu_cable_qty: '2',
}
const templatePreview = computed(() => {
  if (props.mode !== 'desc' || src.value?.kind !== 'template' || !src.value.template) return ''
  return String(src.value.template).replace(/\$\{(\w+)\}/g, (_, k: string) => DEMO_VARS[k] ?? `\${${k}}`)
})

const tplInput = ref<HTMLInputElement | null>(null)
const insertVarSel = ref<string | undefined>(undefined)
function insertVar(key: string) {
  const cur = String(src.value.template || '')
  const el = tplInput.value
  const pos = el ? (el.selectionStart ?? cur.length) : cur.length
  const token = `\${${key}}`
  patch({ template: cur.slice(0, pos) + token + cur.slice(pos) })
  insertVarSel.value = undefined
  nextTick(() => {
    if (el) { el.focus(); const p = pos + token.length; el.setSelectionRange(p, p) }
  })
}

function defaultsFor(kind: string): Record<string, any> {
  switch (kind) {
    case 'fixed': return props.mode === 'desc' ? { value: '' } : { value: 1 }
    case 'part_field': return { category: 'heatsink', field: 'name' }
    case 'part_quantity': return { category: 'fan' }
    case 'template': return { template: '' }
    case 'struct_count': return { scope: props.rowType === 'rear_summary' ? 'rear_all' : 'io_slot' }
    case 'config_value': return { key: 'bays' }
    case 'config_calc': return { key: 'psu_qty' }
    case 'manual': return {}
    default: return {}
  }
}
function onKindChange(kind: any) { src.value = { kind, ...defaultsFor(kind) } }
function patch(p: any) { src.value = { ...src.value, ...p } }
</script>

<template>
  <div class="rs">
    <a-select :value="src.kind" size="small" style="width: 128px" @change="(v: any) => onKindChange(v)">
      <a-select-option v-for="k in kinds" :key="k.value" :value="k.value">{{ k.label }}</a-select-option>
    </a-select>

    <!-- desc 输入 -->
    <template v-if="mode === 'desc'">
      <a-input v-if="src.kind === 'fixed'" :value="src.value" size="small" style="flex:1; min-width: 140px"
        placeholder="如：国标电源线" @update:value="(v: string) => patch({ value: v })" />
      <template v-else-if="src.kind === 'part_field'">
        <a-select :value="src.category" size="small" style="width: 150px" placeholder="选底盘件品类"
          @change="(v: any) => patch({ category: v })">
          <a-select-option v-for="c in CATEGORY_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</a-select-option>
        </a-select>
        <a-select :value="src.field" size="small" style="width: 130px" @change="(v: any) => patch({ field: v })">
          <a-select-option v-for="f in PART_FIELDS" :key="f.value" :value="f.value">{{ f.label }}</a-select-option>
        </a-select>
      </template>
      <div v-else-if="src.kind === 'template'" class="rs-tpl">
        <div class="rs-tpl-row">
          <a-input ref="tplInput" :value="src.template" size="small" style="flex:1; min-width: 160px"
            placeholder="拼描述，点右侧插入变量" @update:value="(v: string) => patch({ template: v })" />
          <a-select v-model:value="insertVarSel" size="small" style="width: 180px" placeholder="＋ 插入变量…"
            @change="(v: any) => insertVar(v)">
            <a-select-option v-for="v in TEMPLATE_VARS" :key="v.key" :value="v.key">{{ v.label }}</a-select-option>
          </a-select>
        </div>
        <div v-if="templatePreview" class="rs-prev">预览（演示值）：{{ templatePreview }}</div>
      </div>
      <a-select v-else-if="src.kind === 'struct_count'" :value="src.scope" size="small" style="width: 230px"
        @change="(v: any) => patch({ scope: v })">
        <a-select-option v-for="s in allowedScopes" :key="s.value" :value="s.value">{{ s.label }}</a-select-option>
      </a-select>
      <a-select v-else-if="src.kind === 'config_value'" :value="src.key" size="small" style="width: 220px"
        @change="(v: any) => patch({ key: v })">
        <a-select-option v-for="k in CONFIG_KEYS_DESC" :key="k.key" :value="k.key">{{ k.label }}</a-select-option>
      </a-select>
      <span v-else class="rs-hint">留空 → 工作台手填</span>
    </template>

    <!-- qty 输入 -->
    <template v-else>
      <a-input-number v-if="src.kind === 'fixed'" :value="src.value" size="small" style="width: 90px"
        @update:value="(v: any) => patch({ value: v ?? 0 })" />
      <a-select v-else-if="src.kind === 'part_quantity'" :value="src.category" size="small" style="width: 150px"
        placeholder="选底盘件品类" @change="(v: any) => patch({ category: v })">
        <a-select-option v-for="c in CATEGORY_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</a-select-option>
      </a-select>
      <a-select v-else-if="src.kind === 'config_calc'" :value="src.key" size="small" style="width: 200px"
        @change="(v: any) => patch({ key: v })">
        <a-select-option v-for="k in CONFIG_KEYS_QTY" :key="k.key" :value="k.key">{{ k.label }}</a-select-option>
      </a-select>
      <span v-else class="rs-hint">留空 → 工作台手填</span>
    </template>
  </div>
</template>

<style scoped>
.rs { display: flex; align-items: center; gap: 6px; flex: 1; flex-wrap: wrap; }
.rs-hint { font-size: 11px; color: var(--cpq-text-muted, #6E7582); font-style: italic; }
.rs-tpl { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 220px; }
.rs-tpl-row { display: flex; align-items: center; gap: 6px; flex: 1; }
.rs-prev { font-size: 11px; line-height: 1.5; color: var(--cpq-text-secondary, #4E5560); background: var(--cpq-overlay-w6, rgba(255,255,255,0.04)); border-radius: 6px; padding: 2px 8px; }
</style>
