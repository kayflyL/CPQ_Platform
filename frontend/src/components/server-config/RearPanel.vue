<script setup lang="ts">
/**
 * 后面板共用组件 —— 基准配置编辑器与服务器配置页同源（视觉统一）。
 * 渲染 PCIe 扩展槽位网格（每槽 opt-block 步进器，数量即选中）+ OCP 网络单选段。
 * 就地改 slot.defaults（option_type 多重集）：配置页传入的 defaults 即 reactive rear[name]，
 * 基准配置传入的 defaults 即 rear_slots[].defaults —— 改动双向回流到各自宿主，无需 emit。
 *
 * 选料 vs 只调数量（同一组件两种模式，由 lockedTypes 驱动，无独立开关）：
 * - 基准配置：lockedTypes 不传 → 每槽显示**全部** option，步进器可选可选数（产默认卡 + 默认数量）。
 * - 配置页：lockedTypes 传基准 defaults 的去重类型 → 该槽只渲染这些卡、只调数量（料自动填好，不能换卡）；
 *   某槽 lockedTypes 为空（旧基准未设默认）→ 该槽回退自由选（向后兼容）。
 *
 * 遵循：[[ocp-is-networking-not-pcie]]（OCP 独立网络分段）。
 */
import { computed } from 'vue'
import { rearOptionQty, rearSlotFilled, rearSetOptionQty, rearDefaultQty, rearDecOption, rearSetSingle } from '@/composables/useRearState'
import type { RearIOSlotOption, RearSlot } from '@/api/serverConfig'
import { optionLabel } from '@/constants/chassisMeta'
import { useAuthStore } from '@/store/auth'

const props = withDefaults(defineProps<{
  slots: RearSlot[]                            // PCIe IO 槽（name + cap + defaults）
  options: Record<string, RearIOSlotOption[]>  // 选项目录（按 series 分桶，rearIOApi 提供）
  ocpSlot?: RearSlot | null                    // OCP 槽（单选语义）；不传则不渲染网络段
  lockedTypes?: Record<string, string[]>       // 配置页：每槽锁定的 option_type（基准 defaults 去重）；缺省/空=自由选
  comboSlots?: string[]                        // 组合槽（fill 模式下首次选默认 1，其余填满 cap）
  firstClick?: 'fill' | 'one'                  // 首次选行为：fill=配置页(组合槽1/其余填cap) | one=逐个+1(基准编辑器作者精确控)
  totals?: { io?: number; ocp?: number }       // 可选：段头金额徽标（配置页传 rearTotal/ocpTotal）
}>(), { comboSlots: () => [] as string[], firstClick: 'fill' })

/** 真实可选 option（去掉 blank 挡片） */
function rawOptions(name: string): RearIOSlotOption[] {
  return (props.options[name] || []).filter(o => o.option_type !== 'blank')
}

/** 该槽要渲染的 option：锁定模式只渲染 lockedTypes 命中的；否则全部 */
function displayOptions(def: RearSlot): RearIOSlotOption[] {
  const locked = props.lockedTypes?.[def.name]
  if (locked && locked.length) {
    const set = new Set(locked)
    return rawOptions(def.name).filter(o => set.has(o.option_type))
  }
  return rawOptions(def.name)
}

const filled = (def: RearSlot) => rearSlotFilled(def.defaults)
const qtyOf = (def: RearSlot, t: string) => rearOptionQty(def.defaults, t)
const canInc = (def: RearSlot) => filled(def) < def.cap
function ensure(def: RearSlot): string[] { return def.defaults || (def.defaults = []) }
function inc(def: RearSlot, t: string) {
  const arr = ensure(def)
  const cur = rearOptionQty(arr, t)
  // 首次选：one=逐个+1（基准编辑器作者精确控，避免一键填满 cap 致 + 灰=锁死）；fill=配置页（组合槽1/其余填cap）
  const next = cur === 0
    ? (props.firstClick === 'one' ? 1 : rearDefaultQty(def.name, def.cap, props.comboSlots))
    : cur + 1
  rearSetOptionQty(arr, t, next, def.cap)
}
function dec(def: RearSlot, t: string) { rearDecOption(ensure(def), t) }
function pickOcp(def: RearSlot, t: string | null) { rearSetSingle(ensure(def), t) }

const auth = useAuthStore()
/** 服务器配置价格可见性（字段级权限；无权限只显示描述标签，价格直接隐藏，不出现 *** 掩码） */
const priceVisible = computed(() => auth.can('field.server.price'))
const ioTotal = computed(() => props.totals?.io)
const ocpTotal = computed(() => props.totals?.ocp)
</script>

<template>
  <div class="sc-section-head"><span class="sh-tag">PCIe 扩展能力</span><span v-if="priceVisible && ioTotal != null" class="sh-amt">¥{{ ioTotal.toLocaleString() }}</span></div>
  <div class="rear-grid" :style="{ gridTemplateColumns: `repeat(${slots.length || 1}, minmax(0,1fr))` }">
    <div class="slot-col" v-for="def in slots" :key="def.name">
      <div class="slot-col-head">
        <slot name="slot-head" :slotData="def">
          <span class="slot-name">{{ def.name }}</span>
          <span class="slot-cap-mini" v-if="def.cap > 1">{{ filled(def) }}/{{ def.cap }}</span>
          <span class="slot-cap-mini" v-else>单卡</span>
        </slot>
      </div>
      <div class="opt-block" v-for="opt in displayOptions(def)" :key="opt.option_type" :class="{ active: qtyOf(def, opt.option_type) > 0 }">
        <span class="opt-info"><span class="opt-label">{{ optionLabel(opt.option_type) }}</span><span v-if="priceVisible" class="opt-price">¥{{ opt.total_price.toLocaleString() }}</span></span>
        <div class="opt-stepper">
          <button :disabled="qtyOf(def, opt.option_type) <= 0" @click="dec(def, opt.option_type)">−</button>
          <span class="opt-qty">{{ qtyOf(def, opt.option_type) }}</span>
          <button :disabled="!canInc(def)" @click="inc(def, opt.option_type)">＋</button>
        </div>
      </div>
      <div class="slot-blank" v-if="displayOptions(def).length === 0"><span class="blank-tag">挡片</span></div>
      <div class="slot-blank" v-else-if="filled(def) === 0"><span class="blank-tag">挡片</span></div>
    </div>
  </div>

  <template v-if="ocpSlot">
    <div class="sc-section-head sh-gap"><span class="sh-tag">网络扩展 · OCP 接口</span><span class="sh-note">OCP 转接适配板 · 支持 OCP 3.0 网络模块，不占 PCIe 槽位</span><span v-if="priceVisible && ocpTotal != null" class="sh-amt">¥{{ ocpTotal.toLocaleString() }}</span></div>
    <div class="net-options">
      <button v-for="opt in displayOptions(ocpSlot)" :key="opt.option_type" :class="['net-card', { active: qtyOf(ocpSlot, opt.option_type) > 0 }]" @click="pickOcp(ocpSlot, opt.option_type)">
        <span class="net-label">{{ optionLabel(opt.option_type) }}</span><span v-if="priceVisible" class="net-price">¥{{ opt.total_price.toLocaleString() }}</span>
      </button>
      <button :class="['net-card', 'blank', { active: filled(ocpSlot) === 0 }]" @click="pickOcp(ocpSlot, null)">
        <span class="net-label">挡片</span><span v-if="priceVisible" class="net-price">¥0</span>
      </button>
    </div>
  </template>
</template>

<style scoped>
.sc-section-head { display: flex; align-items: baseline; gap: 10px; margin: 4px 0 10px; }
.sc-section-head.sh-gap { margin-top: 18px; }
.sc-section-head .sh-tag { font-size: 13px; font-weight: 700; color: var(--cpq-text-primary, #E8ECEF); }
.sc-section-head .sh-note { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.sc-section-head .sh-amt { margin-left: auto; font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary, #1677FF); }

.rear-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.slot-col { display: flex; flex-direction: column; padding: 12px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; min-width: 0; }
.slot-col-head { display: flex; align-items: baseline; gap: 6px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--cpq-overlay-w8); }
.slot-col-head .slot-name { font-weight: 700; font-size: 14px; color: var(--cpq-text-primary, #E8ECEF); }
.slot-cap-mini { font-size: 11px; color: var(--cpq-text-muted, #6E7582); margin-left: auto; }
.opt-block { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 8px 10px; border: 1px solid var(--cpq-overlay-w8); border-radius: 8px; margin-bottom: 8px; background: var(--cpq-overlay-w4); transition: all .2s; }
.opt-info { display: flex; align-items: center; gap: 8px; min-width: 0; }
.opt-label { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.opt-block.active .opt-label { color: var(--cpq-accent-primary, #1677FF); }
.opt-block.active { border-color: var(--cpq-overlay-a40); background: var(--cpq-overlay-a8); box-shadow: 0 0 12px var(--cpq-overlay-a8); }
.opt-price { font-size: 13px; font-weight: 600; color: var(--cpq-text-secondary, #9BA1AA); }
.opt-block.active .opt-price { color: var(--cpq-accent-primary, #1677FF); }
.opt-stepper { display: flex; align-items: center; background: var(--cpq-overlay-b30); border: 1px solid var(--cpq-overlay-w10); border-radius: 6px; overflow: hidden; }
.opt-stepper button { width: 22px; height: 22px; border: none; background: transparent; color: var(--cpq-text-secondary, #9BA1AA); font-size: 13px; cursor: pointer; transition: all .15s; padding: 0; }
.opt-stepper button:hover:not(:disabled) { color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a8); }
.opt-stepper button:disabled { opacity: .3; cursor: not-allowed; }
.opt-qty { min-width: 20px; text-align: center; font-size: 12px; font-weight: 700; color: var(--cpq-accent-primary, #1677FF); }
.slot-blank { padding: 10px 8px; text-align: center; }
.blank-tag { display: inline-block; font-size: 12px; color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w4); border: 1px dashed var(--cpq-overlay-w10); border-radius: 6px; padding: 3px 12px; }
.net-options { display: flex; flex-wrap: wrap; gap: 12px; }
.net-card { flex: 1; min-width: 120px; padding: 12px 16px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; color: var(--cpq-text-secondary, #9BA1AA); cursor: pointer; transition: all .25s; font-family: inherit; font-size: 14px; font-weight: 600; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.net-label { white-space: nowrap; }
.net-card.active .net-label { color: var(--cpq-accent-primary, #1677FF); }
.net-card:hover { border-color: var(--cpq-overlay-w20); color: var(--cpq-text-primary, #E8ECEF); transform: translateY(-1px); }
.net-card.active { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); box-shadow: 0 0 16px var(--cpq-overlay-a20); }
.net-card.blank { flex: 0 0 auto; min-width: 120px; border-style: dashed; }
</style>
