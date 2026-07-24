<script setup lang="ts">
/** KP 单类别卡片 — 一类一卡（CPU / Memory / HDD-SSD / GPU / NIC …）。
 *  行数据来自父组件扁平 kpLines 按 cat 过滤；事件回传父改扁平数组（保持持久化结构不变）。
 *  GPU 卡(quoteMode)额外渲染 GPU 供电线选择（料号库挑 PN + 数量），从机箱弹窗外移至此；成本仍算 L6 机箱。
 *
 *  quoteMode（报价工作台新建模式 opt-in）：每行额外渲染「原始单价 / 利率% / 含税售价」，
 *  线路 final = base_price × (1 + profit_margin/100)；选新 pn 时自动把 base_price 带成料号库单价。
 *  server-config 页不传 quoteMode → 行为完全不变（GPU 线在 L6ChassisConfig 弹窗配）。 */
import PartPicker from '@/components/common/PartPicker.vue'
import type { PickerItem } from '@/types/picker'

interface KpLine { cat: string; pn: string; qty: number; base_price?: number; profit_margin?: number }

const props = defineProps<{
  cat: string
  stepNum: number
  // 行源两种：server-config 的 kpLines({cat,pn,qty}) 与 报价 cfg.items KP 行(含 base_price/profit_margin/pn)。
  // 组件只读 pn/qty/base_price/profit_margin（cat 来自 prop），故用 any[] 放开两侧结构差异
  lines: any[]
  pickerItems: PickerItem[]
  priceOf: (pn: string) => number
  removable?: boolean
  isGpu?: boolean
  /** GPU 供电线（quoteMode + GPU 卡）：料号库挑选 + 数量，状态由父托管(写回 cfg.l6_bom_picks.overrides) */
  gpuCablePn?: string
  gpuCableQty?: number
  gpuCableItems?: PickerItem[]
  quoteMode?: boolean
  /** 报价页 KP 大卡内降级为扁平分段(去玻璃)，配置页不传保持原样玻璃卡 */
  flat?: boolean
}>()

const emit = defineEmits<{
  (e: 'set-line', index: number, patch: Partial<KpLine>): void
  (e: 'del-line', index: number): void
  (e: 'add-line'): void
  (e: 'remove-card'): void
  (e: 'update:gpuCablePn', pn: string): void
  (e: 'update:gpuCableQty', qty: number): void
}>()

const lineCost = (l: KpLine) => (props.priceOf(l.pn) || 0) * (l.qty || 0)
// quote 模式：含税售价/行 = 原始单价 × (1 + 利率/100) × 数量
const quoteLineUnitFinal = (l: KpLine) => (Number(l.base_price) || 0) * (1 + (Number(l.profit_margin) || 0) / 100)
const quoteLineSales = (l: KpLine) => quoteLineUnitFinal(l) * (l.qty || 0)
const cardTotal = () => props.quoteMode
  ? props.lines.reduce((s, l) => s + quoteLineSales(l), 0)
  : props.lines.reduce((s, l) => s + lineCost(l), 0)

// 选新 pn：quote 模式顺带把原始单价带成料号库单价（遵循 [[derive-must-have-manual-fallback]]：之后仍可手改）
function onPick(i: number, pn: any) {
  const p = typeof pn === 'string' ? pn : ''
  if (props.quoteMode) emit('set-line', i, { pn: p, base_price: props.priceOf(p) || 0 })
  else emit('set-line', i, { pn: p })
}
</script>

<template>
  <div :id="`kp-card-${cat}`" class="sc-panel kp-card" :class="{ 'kp-flat': flat }">
    <div class="sc-phead">
      <span class="num">{{ stepNum }}</span>
      <h2>{{ cat }}</h2>
      <span class="hint">{{ pickerItems.length }} 个可选料号</span>
      <span class="amt">¥{{ cardTotal().toLocaleString() }}</span>
      <button v-if="removable" class="kp-del-card" @click="emit('remove-card')">删除卡片</button>
    </div>
    <div class="sc-pbody">
      <!-- GPU 供电线（quoteMode + GPU 卡：从机箱弹窗外移至此，成本仍算 L6 机箱）-->
      <div v-if="isGpu && quoteMode" class="gpu-cable-row">
        <span class="gc-label">GPU 供电线</span>
        <PartPicker class="gc-picker" :items="gpuCableItems || []" :model-value="gpuCablePn || ''" size="small" placeholder="(选择 GPU 供电线)"
          @update:model-value="(pn:any)=>emit('update:gpuCablePn', typeof pn==='string'?pn:'')" />
        <div class="sc-step">
          <button @click="emit('update:gpuCableQty', Math.max(0, (gpuCableQty || 0) - 1))">−</button>
          <input :value="gpuCableQty || 0" @change="(e:any)=>emit('update:gpuCableQty', parseInt(e.target.value) || 0)" />
          <button @click="emit('update:gpuCableQty', (gpuCableQty || 0) + 1)">+</button>
        </div>
      </div>

      <!-- server-config 模式：单行（picker + 数量 + 行价 + 删除）-->
      <template v-if="!quoteMode">
        <div class="sc-kp-line" v-for="(l, i) in lines" :key="i">
          <PartPicker :items="pickerItems" :model-value="l.pn" size="small" placeholder="(请选择)"
            @update:model-value="(pn:any)=>onPick(i, pn)" />
          <div class="sc-step">
            <button @click="emit('set-line', i, { qty: Math.max(0, l.qty - 1) })">−</button>
            <input :value="l.qty" @change="(e:any)=>emit('set-line', i, { qty: parseInt(e.target.value) || 0 })" />
            <button @click="emit('set-line', i, { qty: l.qty + 1 })">+</button>
          </div>
          <span class="sc-kp-price">¥{{ lineCost(l).toLocaleString() }}</span>
          <button class="sc-del" @click="emit('del-line', i)" title="删除该行">✕</button>
        </div>
      </template>

      <!-- quote 模式：两行（上=picker+数量+删除，下=原始单价/利率%/含税售价）-->
      <template v-else>
        <template v-for="(l, i) in lines" :key="i">
          <div class="sc-kp-line qm-line">
            <PartPicker class="qm-picker" :items="pickerItems" :model-value="l.pn" size="small" placeholder="(请选择)"
              @update:model-value="(pn:any)=>onPick(i, pn)" />
            <div class="sc-step">
              <button @click="emit('set-line', i, { qty: Math.max(0, l.qty - 1) })">−</button>
              <input :value="l.qty" @change="(e:any)=>emit('set-line', i, { qty: parseInt(e.target.value) || 0 })" />
              <button @click="emit('set-line', i, { qty: l.qty + 1 })">+</button>
            </div>
            <button class="sc-del" @click="emit('del-line', i)" title="删除该行">✕</button>
          </div>
          <div class="qm-fields">
            <div class="qm-field">
              <label>原始单价</label>
              <a-input-number :value="l.base_price" @change="(v:any)=>emit('set-line', i, { base_price: Number(v) || 0 })"
                size="small" :precision="2" style="width:100%" />
            </div>
            <div class="qm-field">
              <label>利率%</label>
              <a-input-number :value="l.profit_margin" @change="(v:any)=>emit('set-line', i, { profit_margin: Number(v) || 0 })"
                size="small" :min="0" style="width:100%" />
            </div>
            <div class="qm-field">
              <label>含税售价</label>
              <span class="qm-final">¥ {{ quoteLineSales(l).toLocaleString() }}</span>
            </div>
          </div>
        </template>
      </template>

      <div v-if="!lines.length" class="sc-empty">暂无{{ cat }}行，点下方添加。</div>
      <button class="sc-add" @click="emit('add-line')">+ 添加{{ cat }}</button>
    </div>
  </div>
</template>

<style scoped>
.sc-panel {
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); border-radius: 18px; overflow: hidden;
  box-shadow: 0 22px 64px var(--cpq-shadow-color-strong), 0 0 34px var(--cpq-overlay-a4), inset 0 1px 0 var(--cpq-overlay-w15), inset 0 -18px 48px var(--cpq-shadow-color-soft);
}
/* flat 模式：报价页 KP 大卡内降级为扁平分段（去玻璃避嵌套，配置页不受影响）*/
.sc-panel.kp-flat {
  background: var(--cpq-overlay-w4);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: none;
  border-color: var(--cpq-overlay-w10);
  border-radius: 14px;
}
.sc-panel.kp-flat .sc-phead { background: transparent; border-bottom-color: var(--cpq-overlay-w8); }
.sc-panel.kp-flat:hover { border-color: var(--cpq-overlay-w20); }
.sc-phead { display: flex; align-items: center; gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w4); }
.sc-phead .num { width: 26px; height: 26px; border-radius: 7px; background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary,#1677FF); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
.sc-phead h2 { font-size: 16px; font-weight: 600; margin: 0; color: var(--cpq-text-primary, #E8ECEF); }
.sc-phead .hint { color: var(--cpq-text-muted,#6E7582); font-size: 12px; }
.sc-phead .amt { margin-left: auto; color: var(--cpq-accent-primary,#1677FF); font-weight: 700; font-size: 14px; }
.kp-del-card { margin-left: 8px; padding: 4px 10px; border: 1px solid var(--cpq-overlay-w20); border-radius: 7px;
  background: transparent; color: var(--cpq-text-muted,#6E7582); font-size: 12px; cursor: pointer; transition: all .2s; }
.kp-del-card:hover { color: var(--cpq-accent-danger); border-color: rgba(255,107,107,.4); }
.sc-pbody { padding: 18px 20px; }
/* GPU 供电线行（quoteMode + GPU 卡）：蓝色调区分于普通 KP 行，表"机箱线缆"语义 */
.gpu-cable-row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; margin-bottom: 12px;
  background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a20); border-radius: 10px; }
.gc-label { font-size: 12px; font-weight: 600; color: var(--cpq-accent-primary,#1677FF); white-space: nowrap; flex-shrink: 0; }
.gc-picker { flex: 1; min-width: 0; }
.gpu-cable-row .sc-step { flex-shrink: 0; }
.sc-kp-line { display: grid; grid-template-columns: 1fr 130px 100px 32px; gap: 9px; align-items: center; margin-bottom: 9px; }
.sc-step { display: flex; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; overflow: hidden; }
.sc-step button { width: 30px; color: var(--cpq-text-secondary,#9BA1AA); font-size: 14px; background: transparent; border: none; cursor: pointer; transition: all .2s; }
.sc-step button:hover { color: var(--cpq-accent-primary,#1677FF); }
.sc-step input { width: 100%; min-width: 0; text-align: center; border: none; background: transparent; color: var(--cpq-text-primary,#E8ECEF); font-size: 13px; outline: none; }
.sc-kp-price { font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); text-align: right; }
.sc-del { width: 30px; height: 34px; border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; background: transparent; color: var(--cpq-text-muted,#6E7582); cursor: pointer; transition: all .2s; }
.sc-del:hover { color: var(--cpq-accent-danger); border-color: rgba(255,107,107,.4); }
.sc-empty { color: var(--cpq-text-muted,#6E7582); text-align: center; padding: 14px; font-size: 13px; }
.sc-add { margin-top: 5px; padding: 7px 14px; border: 1px dashed var(--cpq-overlay-w20); border-radius: 8px; background: transparent; color: var(--cpq-text-secondary,#9BA1AA); cursor: pointer; font-size: 13px; transition: all .2s; }
.sc-add:hover { border-color: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-primary,#1677FF); background: var(--cpq-overlay-a8); }

/* ---- quote 模式（报价工作台新建模式）行布局 ---- */
.sc-kp-line.qm-line { grid-template-columns: 1fr 130px 32px; margin-bottom: 6px; }
.qm-picker { min-width: 0; }
.qm-fields {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px;
  align-items: center; margin-bottom: 12px; padding: 9px 12px;
  background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 10px;
}
.qm-field { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.qm-field label { font-size: 10px; color: var(--cpq-text-muted,#6E7582); text-transform: uppercase; letter-spacing: .5px; }
.qm-final {
  font-size: 14px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF);
  font-variant-numeric: tabular-nums; line-height: 28px;
}
.qm-fields :deep(.ant-input-number) { width: 100%; }
.qm-fields :deep(.ant-input-number-input) {
  background: transparent !important; color: var(--cpq-text-primary, #E8ECEF) !important; font-size: 13px;
}
</style>
